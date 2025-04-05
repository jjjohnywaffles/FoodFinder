import os
import sys
import time
import random
import json
import requests
import geocoder  # For IP-based "Find Restaurants Near Me"

from geopy.geocoders import Nominatim
from geopy.distance import geodesic

from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QLineEdit,
    QPushButton, QStackedWidget, QSplitter, QListWidget, QListWidgetItem,
    QLabel, QTextEdit, QMessageBox, QCheckBox, QProgressBar, QFrame, QGraphicsOpacityEffect,
    QTabWidget, QComboBox, QScrollArea
)
from PySide6.QtCore import Qt, QThread, Signal, QTimer, QPropertyAnimation
from PySide6.QtGui import QPixmap, QIcon, QFont

# Replace with your actual Google Places API Key.
GOOGLE_PLACES_API_KEY = "REPLACE WITH GOOGLE API KEY"

# -----------------------------
# Global Caches for Optimization
# -----------------------------
geocode_cache = {}   # { location_query : (lat, lon) }
places_cache = {}    # { location_query : [results, ...] }
image_cache = {}     # { (photo_reference, max_width) : QPixmap }

# -----------------------------
# Updated Style Sheets with Rounded Corners
# -----------------------------
LIGHT_STYLE = """ 
QMainWindow { background-color: #F0F2F5; border-radius: 15px; }
QLabel { color: #1c1e21; font-family: "Segoe UI", sans-serif; }
QPushButton {
    background-color: #1877F2; color: white;
    border: none; border-radius: 10px;
    padding: 8px 12px; font-family: "Segoe UI", sans-serif; font-size: 14px;
}
QPushButton:hover { background-color: #166FE5; }
QLineEdit, QListWidget, QTextEdit {
    background-color: white; border: 1px solid #CED0D4;
    border-radius: 10px; padding: 8px; font-family: "Segoe UI", sans-serif; font-size: 14px;
    color: #1c1e21;
}
QSplitter { background-color: transparent; }
QListWidget { padding: 5px; }
QTabWidget::pane { border: none; background-color: #F0F2F5; border-radius: 10px; }
QTabBar::tab { background-color: #F0F2F5; color: #1c1e21; padding: 10px; border-radius: 10px; }
QTabBar::tab:selected { background-color: #1877F2; color: white; }
"""

DARK_STYLE = """
QMainWindow { background-color: #2C2F33; border-radius: 15px; }
QLabel { color: #DCDDDE; font-family: "Segoe UI", sans-serif; }
QPushButton {
    background-color: #7289DA; color: white;
    border: none; border-radius: 10px;
    padding: 8px 12px; font-family: "Segoe UI", sans-serif; font-size: 14px;
}
QPushButton:hover { background-color: #677BC4; }
QLineEdit, QListWidget, QTextEdit {
    background-color: #23272A; border: 1px solid #2C2F33;
    border-radius: 10px; padding: 8px; font-family: "Segoe UI", sans-serif; font-size: 14px;
    color: #DCDDDE;
}
QSplitter { background-color: transparent; }
QListWidget { padding: 5px; }
QTabWidget::pane { border: none; background-color: #23272A; border-radius: 10px; }
QTabBar::tab { background-color: #23272A; color: #DCDDDE; padding: 10px; border-radius: 10px; }
QTabBar::tab:selected { background-color: #7289DA; }
"""

# -----------------------------
# RestaurantSearchWorker (Optimized for initial search)
# -----------------------------
class RestaurantSearchWorker(QThread):
    results_ready = Signal(list)
    error_occurred = Signal(str)

    def __init__(self, location_query, parent=None):
        super().__init__(parent)
        self.location_query = location_query
        self.radius = 5000  # 5 km
        self.center = None
        self.max_pages = 1  # Fetch only the first page

    def run(self):
        try:
            if self.location_query in places_cache:
                self.results_ready.emit(places_cache[self.location_query])
                return

            if self.location_query in geocode_cache:
                lat, lon = geocode_cache[self.location_query]
            else:
                try:
                    parts = self.location_query.split(',')
                    if len(parts) == 2:
                        lat = float(parts[0].strip())
                        lon = float(parts[1].strip())
                    else:
                        raise ValueError
                except ValueError:
                    query = self.location_query.strip()
                    if ',' not in query:
                        query = f"{query}, USA"
                    geolocator = Nominatim(user_agent="restaurant_finder_app")
                    location = geolocator.geocode(query)
                    if not location:
                        raise Exception("Unable to geocode the provided location.")
                    lat, lon = location.latitude, location.longitude
                geocode_cache[self.location_query] = (lat, lon)

            self.center = (lat, lon)
            url = "https://maps.googleapis.com/maps/api/place/nearbysearch/json"
            params = {
                "location": f"{lat},{lon}",
                "radius": self.radius,
                "type": "restaurant",
                "key": GOOGLE_PLACES_API_KEY
            }
            results = []
            page_count = 0
            while True:
                response = requests.get(url, params=params)
                if response.status_code != 200:
                    raise Exception(f"Google Places API error: {response.status_code}")
                data = response.json()
                if data.get("status") not in ("OK", "ZERO_RESULTS"):
                    raise Exception(f"Google Places API error: {data.get('status')}")
                results.extend(data.get("results", []))
                page_count += 1
                next_page_token = data.get("next_page_token")
                if next_page_token and page_count < self.max_pages:
                    params["pagetoken"] = next_page_token
                    time.sleep(2)
                else:
                    break
            places_cache[self.location_query] = results
            self.results_ready.emit(results)
        except Exception as e:
            self.error_occurred.emit(str(e))

# -----------------------------
# WelcomePage (Landing Page)
# -----------------------------
class WelcomePage(QWidget):
    searchInitiated = Signal(str)
    darkModeToggled = Signal(bool)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.loadingDots = 0
        self.loadingTimer = None

        layout = QVBoxLayout()
        layout.addStretch()

        top_bar = QHBoxLayout()
        top_bar.addStretch()
        self.darkModeCheckBox = QCheckBox("Dark Mode")
        self.darkModeCheckBox.setStyleSheet("""
            QCheckBox { spacing: 10px; }
            QCheckBox::indicator { width: 40px; height: 20px; border-radius: 10px; }
            QCheckBox::indicator:unchecked { border: 1px solid #b3b3b3; background-color: #b3b3b3; }
            QCheckBox::indicator:checked { border: 1px solid #1877F2; background-color: #1877F2; }
        """)
        top_bar.addWidget(self.darkModeCheckBox)
        layout.addLayout(top_bar)

        title_frame = QFrame()
        title_frame.setFrameShape(QFrame.Box)
        title_frame.setStyleSheet("border: 2px solid #CED0D4; border-radius: 15px;")
        title_layout = QVBoxLayout(title_frame)
        title_label = QLabel("Food Finder")
        title_label.setFont(QFont("Segoe UI", 32, QFont.Bold))
        title_label.setAlignment(Qt.AlignCenter)
        title_layout.addWidget(title_label)
        layout.addWidget(title_frame, alignment=Qt.AlignCenter)
        layout.addSpacing(10)

        subtitle_label = QLabel("Find the best restaurants near you.")
        subtitle_label.setFont(QFont("Segoe UI", 18))
        subtitle_label.setAlignment(Qt.AlignCenter)
        layout.addWidget(subtitle_label)
        layout.addSpacing(20)

        search_bar_container = QHBoxLayout()
        self.location_input = QLineEdit()
        self.location_input.setPlaceholderText("Enter Zip Code or City Name (e.g., 90210 or New York)")
        self.location_input.setFixedWidth(400)
        search_bar_container.addStretch()
        search_bar_container.addWidget(self.location_input)
        search_bar_container.addStretch()
        layout.addLayout(search_bar_container)
        layout.addSpacing(20)

        button_layout = QHBoxLayout()
        button_layout.addStretch()
        self.search_button = QPushButton("Search")
        self.search_button.setFixedWidth(200)
        self.findNearMeButton = QPushButton("Find Restaurants Near Me")
        self.findNearMeButton.setFixedWidth(200)
        button_layout.addWidget(self.search_button)
        button_layout.addSpacing(20)
        button_layout.addWidget(self.findNearMeButton)
        button_layout.addStretch()
        layout.addLayout(button_layout)

        layout.addStretch()

        self.loadingBar = QProgressBar()
        self.loadingBar.setRange(0, 0)
        self.loadingBar.setVisible(False)
        self.loadingBar.setFixedWidth(800)
        layout.addWidget(self.loadingBar, alignment=Qt.AlignCenter)
        layout.addStretch()

        self.setLayout(layout)

        self.search_button.clicked.connect(self.onSearchClicked)
        self.findNearMeButton.clicked.connect(self.onFindNearMeClicked)
        self.darkModeCheckBox.toggled.connect(lambda checked: self.darkModeToggled.emit(checked))

    def onSearchClicked(self):
        self.animateButtonClick(self.search_button)
        self.startLoadingAnimation()
        location = self.location_input.text().strip()
        if not location:
            QMessageBox.warning(self, "Input Error", "Please enter a valid location.")
            self.stopLoadingAnimation()
            return
        self.searchInitiated.emit(location)

    def onFindNearMeClicked(self):
        self.animateButtonClick(self.findNearMeButton)
        self.startLoadingAnimation()
        g = geocoder.ip('me')
        if g.ok and g.latlng:
            lat, lon = g.latlng
            location_str = f"{lat}, {lon}"
            self.searchInitiated.emit(location_str)
        else:
            QMessageBox.warning(self, "Location Error", "Unable to determine your location.")
            self.stopLoadingAnimation()

    def animateButtonClick(self, button):
        effect = QGraphicsOpacityEffect(button)
        button.setGraphicsEffect(effect)
        anim = QPropertyAnimation(effect, b"opacity", self)
        anim.setDuration(150)
        anim.setStartValue(1)
        anim.setKeyValueAt(0.5, 0.5)
        anim.setEndValue(1)
        anim.start(QPropertyAnimation.DeleteWhenStopped)

    def startLoadingAnimation(self):
        self.loadingDots = 0
        self.search_button.setEnabled(False)
        self.findNearMeButton.setEnabled(False)
        self.loadingBar.setVisible(True)
        self.loadingTimer = QTimer(self)
        self.loadingTimer.timeout.connect(self.updateLoadingText)
        self.loadingTimer.start(500)

    def updateLoadingText(self):
        self.loadingDots = (self.loadingDots + 1) % 4
        self.search_button.setText("Searching" + "." * self.loadingDots)
        self.findNearMeButton.setText("Searching" + "." * self.loadingDots)

    def stopLoadingAnimation(self):
        if self.loadingTimer:
            self.loadingTimer.stop()
            self.loadingTimer = None
        self.loadingBar.setVisible(False)
        self.search_button.setEnabled(True)
        self.findNearMeButton.setEnabled(True)
        self.search_button.setText("Search")
        self.findNearMeButton.setText("Find Restaurants Near Me")

# -----------------------------
# UpdatedSearchPage (Main App with Favorites, Persistence & Dark Mode for Details)
# -----------------------------
class UpdatedSearchPage(QWidget):
    searchInitiated = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.dark_mode = False
        self.photoReferences = []
        self.originalPixmaps = []
        self.currentPhotoIndex = 0
        self.all_restaurants = []  # Full search results
        self.favorites = []        # List of favorited restaurant dicts

        main_layout = QVBoxLayout(self)

        # --- Top Bar ---
        top_bar = QHBoxLayout()
        foodFinderLabel = QLabel("GeoGrub")
        foodFinderLabel.setFont(QFont("Segoe UI", 20, QFont.Bold))
        top_bar.addWidget(foodFinderLabel)
        top_bar.addStretch()
        self.location_input = QLineEdit()
        self.location_input.setPlaceholderText("Enter Zip Code or City Name")
        self.location_input.setFixedWidth(300)
        top_bar.addWidget(self.location_input)
        top_bar.addStretch()
        self.search_button = QPushButton("Search")
        self.search_button.setFixedWidth(150)
        self.random_button = QPushButton("Select Random Restaurant")
        self.random_button.setFixedWidth(200)
        top_bar.addWidget(self.search_button)
        top_bar.addWidget(self.random_button)
        self.darkModeToggle = QCheckBox("Dark Mode")
        top_bar.addWidget(self.darkModeToggle)
        self.darkModeToggle.toggled.connect(lambda checked: self.window().setDarkMode(checked))
        main_layout.addLayout(top_bar)

        # --- Left Panel with Tabs for Filters and Favorites ---
        left_tab_widget = QTabWidget()
        left_tab_widget.setMinimumWidth(300)

        # Search Results Tab with Filters
        search_tab = QWidget()
        search_tab_layout = QVBoxLayout(search_tab)
        filter_panel = QFrame()
        filter_layout = QVBoxLayout(filter_panel)
        filter_layout.addWidget(QLabel("<b>Filters</b>"))
        cuisine_layout = QHBoxLayout()
        cuisine_layout.addWidget(QLabel("Cuisine:"))
        self.cuisine_combo = QComboBox()
        self.cuisine_combo.addItems([
            "All", "Italian", "Chinese", "Japanese", "Mexican", "Indian", "Thai", "Mediterranean",
            "French", "American", "Korean", "Vietnamese", "Greek", "Spanish", "Lebanese", "Turkish",
            "Caribbean", "Brazilian", "German", "British", "Fusion"
        ])
        cuisine_layout.addWidget(self.cuisine_combo)
        filter_layout.addLayout(cuisine_layout)
        price_layout = QHBoxLayout()
        price_layout.addWidget(QLabel("Price:"))
        self.price_combo = QComboBox()
        self.price_combo.addItems(["All", "$", "$$", "$$$", "$$$$"])
        price_layout.addWidget(self.price_combo)
        filter_layout.addLayout(price_layout)
        self.open_now_checkbox = QCheckBox("Open Now")
        filter_layout.addWidget(self.open_now_checkbox)
        apply_filters_button = QPushButton("Apply Filters")
        filter_layout.addWidget(apply_filters_button)
        search_tab_layout.addWidget(filter_panel)
        self.restaurant_list = QListWidget()
        search_tab_layout.addWidget(self.restaurant_list)
        left_tab_widget.addTab(search_tab, "Search Results")

        # Favorites Tab
        favorites_tab = QWidget()
        favorites_layout = QVBoxLayout(favorites_tab)
        self.favorites_list = QListWidget()
        favorites_layout.addWidget(self.favorites_list)
        left_tab_widget.addTab(favorites_tab, "Favorites")
        self.loadFavorites()
        self.favorites_list.itemClicked.connect(self.onFavoriteClicked)

        # --- Main Splitter (Left Panel + Details) ---
        splitter = QSplitter(Qt.Horizontal)
        splitter.addWidget(left_tab_widget)

        # Details Panel in Scroll Area.
        details_widget = QWidget()
        self.details_widget = details_widget  # Save for dark mode updates
        details_layout = QVBoxLayout(details_widget)
        details_layout.setAlignment(Qt.AlignTop)
        name_container = QWidget()
        name_layout = QVBoxLayout(name_container)
        self.details_name_label = QLabel("<b>Name:</b>")
        self.details_name_label.setAlignment(Qt.AlignCenter)
        self.details_name_label.setFont(QFont("Segoe UI", 28, QFont.Bold))
        name_layout.addWidget(self.details_name_label)
        details_layout.addWidget(name_container)
        # Image Gallery
        self.imageFrame = QFrame()
        self.imageFrame.setFixedSize(510, 360)
        self.imageFrame.setStyleSheet("border-radius: 15px;")
        frame_layout = QVBoxLayout(self.imageFrame)
        frame_layout.setContentsMargins(5, 5, 5, 5)
        frame_layout.setAlignment(Qt.AlignCenter)
        self.details_image_label = QLabel()
        self.details_image_label.setAlignment(Qt.AlignCenter)
        self.details_image_label.setFixedSize(500, 350)
        frame_layout.addWidget(self.details_image_label)
        imageContainerLayout = QHBoxLayout()
        self.imageLeftButton = QPushButton("<")
        self.imageLeftButton.setFixedWidth(30)
        self.imageRightButton = QPushButton(">")
        self.imageRightButton.setFixedWidth(30)
        imageContainerLayout.addWidget(self.imageLeftButton)
        imageContainerLayout.addWidget(self.imageFrame)
        imageContainerLayout.addWidget(self.imageRightButton)
        imageContainerLayout.setAlignment(Qt.AlignCenter)
        details_layout.addLayout(imageContainerLayout)
        self.imageLeftButton.clicked.connect(self.showPreviousImage)
        self.imageRightButton.clicked.connect(self.showNextImage)
        # Address
        self.details_address_label = QLabel("<b>Address:</b>")
        self.details_address_label.setAlignment(Qt.AlignCenter)
        self.details_address_label.setTextInteractionFlags(Qt.TextBrowserInteraction)
        self.details_address_label.setOpenExternalLinks(True)
        self.details_address_label.setFont(QFont("Segoe UI", 12))
        details_layout.addWidget(self.details_address_label)
        # Info Bubbles and Favorites Button (styled like bubbles)
        bubbleLayout = QHBoxLayout()
        self.phoneBubble = QLabel()
        self.ratingBubble = QLabel()
        self.websiteBubble = QLabel()
        self.priceBubble = QLabel()
        self.setBubbleStyles(self.dark_mode)
        bubbleLayout.addWidget(self.phoneBubble)
        bubbleLayout.addWidget(self.ratingBubble)
        bubbleLayout.addWidget(self.websiteBubble)
        bubbleLayout.addWidget(self.priceBubble)
        self.fav_button = QPushButton("Add to Favorites")
        self.fav_button.setFixedSize(120, 30)
        self.updateFavoriteButton(favorited=False)
        self.fav_button.clicked.connect(self.addToFavorites)
        bubbleLayout.addWidget(self.fav_button)
        bubbleLayout.setAlignment(Qt.AlignCenter)
        details_layout.addLayout(bubbleLayout)
        # Reviews Section
        self.reviewHeader = QLabel("<b>Reviews:</b>")
        self.reviewHeader.setFont(QFont("Segoe UI", 20))
        details_layout.addWidget(self.reviewHeader)
        self.details_reviews_text = QTextEdit()
        self.details_reviews_text.setReadOnly(True)
        self.details_reviews_text.setMinimumHeight(300)
        details_layout.addWidget(self.details_reviews_text)
        # AI Summary Section
        ai_summary_label = QLabel("<b>AI Summary:</b>")
        ai_summary_label.setFont(QFont("Segoe UI", 18))
        details_layout.addWidget(ai_summary_label)
        self.ai_summary_text = QTextEdit()
        self.ai_summary_text.setReadOnly(True)
        self.ai_summary_text.setMinimumHeight(100)
        details_layout.addWidget(self.ai_summary_text)

        details_scroll = QScrollArea()
        details_scroll.setWidgetResizable(True)
        details_scroll.setWidget(details_widget)
        splitter.addWidget(details_scroll)
        splitter.setStretchFactor(1, 3)
        main_layout.addWidget(splitter)
        self.setLayout(main_layout)

        self.search_button.clicked.connect(self.onSearchClicked)
        self.random_button.clicked.connect(self.onRandomClicked)
        self.restaurant_list.itemClicked.connect(self.onRestaurantClicked)
        apply_filters_button.clicked.connect(self.applyFilters)

    def setBubbleStyles(self, dark_mode: bool):
        if dark_mode:
            style = """
                background-color: #40444B;
                color: #DCDDDE;
                border-radius: 10px;
                padding: 5px;
                margin: 2px;
                font-family: "Segoe UI", sans-serif;
                font-size: 13px;
            """
        else:
            style = """
                background-color: #E0E0E0;
                color: black;
                border-radius: 10px;
                padding: 5px;
                margin: 2px;
                font-family: "Segoe UI", sans-serif;
                font-size: 13px;
            """
        for widget in [self.phoneBubble, self.ratingBubble, self.websiteBubble, self.priceBubble]:
            widget.setStyleSheet(style)
            widget.setAlignment(Qt.AlignCenter)

    def updateFavoriteButton(self, favorited):
        if favorited:
            self.fav_button.setText("Favorited")
            self.fav_button.setStyleSheet("background-color: green; color: white; border-radius: 10px;")
        else:
            self.fav_button.setText("Add to Favorites")
            self.fav_button.setStyleSheet("")

    def loadFavorites(self):
        try:
            with open("favorites.json", "r") as f:
                self.favorites = json.load(f)
        except Exception:
            self.favorites = []
        self.favorites_list.clear()
        for fav in self.favorites:
            item = QListWidgetItem(fav.get("name", "Unnamed"))
            item.setData(Qt.UserRole, fav)
            self.favorites_list.addItem(item)

    def saveFavorites(self):
        try:
            with open("favorites.json", "w") as f:
                json.dump(self.favorites, f)
        except Exception as e:
            print("Error saving favorites:", e)

    def onFavoriteClicked(self, item: QListWidgetItem):
        restaurant = item.data(Qt.UserRole)
        if restaurant:
            self.showRestaurantDetails(restaurant)

    def applyFilters(self):
        selected_cuisine = self.cuisine_combo.currentText()
        selected_price = self.price_combo.currentText()
        open_now = self.open_now_checkbox.isChecked()

        filtered = []
        for rest in self.all_restaurants:
            if selected_price != "All":
                mapping = {"$": 1, "$$": 2, "$$$": 3, "$$$$": 4}
                if rest.get("price_level", 0) != mapping.get(selected_price, 0):
                    continue
            if open_now:
                if not rest.get("opening_hours", {}).get("open_now", False):
                    continue
            if selected_cuisine != "All":
                types = rest.get("types", [])
                # Check for exact match ignoring case.
                if selected_cuisine.lower() not in [t.lower() for t in types]:
                    continue
            filtered.append(rest)

        self.restaurant_list.clear()
        for rest in filtered:
            name = rest.get("name", "Unnamed")
            vicinity = rest.get("vicinity", "No address")
            item_text = f"{name}\n{vicinity}"
            item = QListWidgetItem(item_text)
            item.setData(Qt.UserRole, rest)
            if "photos" in rest and rest["photos"]:
                photo_ref = rest["photos"][0].get("photo_reference")
                pixmap = self.get_photo_pixmap(photo_ref, max_width=100)
                if pixmap:
                    item.setIcon(QIcon(pixmap))
            self.restaurant_list.addItem(item)
        if self.restaurant_list.count() > 0:
            first_item = self.restaurant_list.item(0)
            self.restaurant_list.setCurrentItem(first_item)
            self.onRestaurantClicked(first_item)

    def onSearchClicked(self):
        location = self.location_input.text().strip()
        if not location:
            QMessageBox.warning(self, "Input Error", "Please enter a valid location.")
            return
        self.searchInitiated.emit(location)

    def onRandomClicked(self):
        count = self.restaurant_list.count()
        if count == 0:
            QMessageBox.information(self, "No Restaurants", "No restaurants available to choose from.")
            return
        index = random.randint(0, count - 1)
        item = self.restaurant_list.item(index)
        self.restaurant_list.setCurrentItem(item)
        self.onRestaurantClicked(item)

    def onRestaurantClicked(self, item: QListWidgetItem):
        restaurant = item.data(Qt.UserRole)
        place_id = restaurant.get("place_id")
        if place_id:
            try:
                details = self.fetchRestaurantDetails(place_id)
                self.showRestaurantDetails(details)
            except Exception as e:
                QMessageBox.critical(self, "Details Error", str(e))

    def fetchRestaurantDetails(self, place_id):
        url = "https://maps.googleapis.com/maps/api/place/details/json"
        params = {
            "place_id": place_id,
            "fields": "place_id,name,formatted_address,formatted_phone_number,website,rating,price_level,reviews,photos",
            "key": GOOGLE_PLACES_API_KEY
        }
        response = requests.get(url, params=params)
        if response.status_code != 200:
            raise Exception("Failed to fetch details: HTTP " + str(response.status_code))
        data = response.json()
        if data.get("status") != "OK":
            raise Exception("Details API error: " + data.get("status"))
        return data.get("result", {})

    def showRestaurantDetails(self, details):
        self.current_details = details
        self.details_name_label.setText(details.get("name", "N/A"))
        address = details.get("formatted_address", "N/A")
        maps_url = f"https://www.google.com/maps/search/?api=1&query={address.replace(' ', '+')}"
        self.details_address_label.setText(f"<b>Address:</b> <a href='{maps_url}'>{address}</a>")
        phone = details.get("formatted_phone_number", "N/A")
        self.phoneBubble.setText(f"📞 {phone}")
        rating = details.get("rating", "N/A")
        self.ratingBubble.setText(f"⭐ {rating}")
        website = details.get("website", "N/A")
        if website != "N/A":
            self.websiteBubble.setText(f'<a href="{website}">🌐 Website</a>')
            self.websiteBubble.setTextInteractionFlags(Qt.TextBrowserInteraction)
            self.websiteBubble.setOpenExternalLinks(True)
        else:
            self.websiteBubble.setText("🌐 N/A")
        price_level = details.get("price_level")
        if price_level is not None:
            price_mapping = {0: "Free", 1: "$", 2: "$$", 3: "$$$", 4: "$$$$"}
            price_text = price_mapping.get(price_level, "N/A")
        else:
            price_text = "N/A"
        self.priceBubble.setText(f"💲 {price_text}")

        # Update favorite button state based on whether the restaurant is already favorited.
        is_favorited = any(r.get("place_id") == details.get("place_id") for r in self.favorites)
        self.updateFavoriteButton(favorited=is_favorited)

        if "photos" in details and details["photos"]:
            photos = details["photos"]
            self.photoReferences = [photo.get("photo_reference") for photo in photos[:5]]
            self.originalPixmaps = []
            for ref in self.photoReferences:
                pix = self.get_photo_pixmap(ref, max_width=500)
                if pix is None:
                    pix = QPixmap()
                self.originalPixmaps.append(pix)
            self.currentPhotoIndex = 0
            self.updateImage()
        else:
            self.photoReferences = []
            self.originalPixmaps = []
            self.details_image_label.clear()

        reviews = details.get("reviews", [])
        reviews_html = ""
        if reviews:
            for review in reviews:
                author = review.get("author_name", "Anonymous")
                rev_rating = review.get("rating", "N/A")
                text = review.get("text", "")
                reviews_html += f"<p><b>{author}</b> (Rating: {rev_rating})<br>{text}</p><hr>"
        else:
            reviews_html = "<p><i>No reviews available.</i></p>"
        self.details_reviews_text.setHtml(reviews_html)
        self.ai_summary_text.setText("AI Summary not available yet. Feature coming soon!")

    def updateImage(self):
        if self.originalPixmaps and len(self.originalPixmaps) > 0:
            fixed_size = self.details_image_label.size()
            pixmap = self.originalPixmaps[self.currentPhotoIndex]
            if not pixmap.isNull():
                scaled_pixmap = pixmap.scaled(fixed_size, Qt.KeepAspectRatio, Qt.SmoothTransformation)
                self.details_image_label.setPixmap(scaled_pixmap)
            else:
                self.details_image_label.clear()

    def showPreviousImage(self):
        if self.photoReferences and self.originalPixmaps:
            self.currentPhotoIndex = (self.currentPhotoIndex - 1) % len(self.photoReferences)
            self.updateImage()

    def showNextImage(self):
        if self.photoReferences and self.originalPixmaps:
            self.currentPhotoIndex = (self.currentPhotoIndex + 1) % len(self.photoReferences)
            self.updateImage()

    def addToFavorites(self):
        if hasattr(self, 'current_details'):
            current_restaurant = self.current_details
            # Check if already favorited
            existing = next((r for r in self.favorites if r.get("place_id") == current_restaurant.get("place_id")), None)
            if existing:
                # Remove from favorites
                self.favorites = [r for r in self.favorites if r.get("place_id") != current_restaurant.get("place_id")]
                # Update the favorites list UI
                for i in range(self.favorites_list.count()):
                    item = self.favorites_list.item(i)
                    if item.data(Qt.UserRole).get("place_id") == current_restaurant.get("place_id"):
                        self.favorites_list.takeItem(i)
                        break
                self.updateFavoriteButton(favorited=False)
                QMessageBox.information(self, "Removed", f"{current_restaurant.get('name', 'Unnamed')} removed from favorites.")
            else:
                # Add to favorites
                self.favorites.append(current_restaurant)
                item = QListWidgetItem(current_restaurant.get("name", "Unnamed"))
                item.setData(Qt.UserRole, current_restaurant)
                self.favorites_list.addItem(item)
                self.updateFavoriteButton(favorited=True)
                QMessageBox.information(self, "Favorite Added", f"{current_restaurant.get('name', 'Unnamed')} added to favorites.")
            self.saveFavorites()

    def get_photo_pixmap(self, photo_reference, max_width=200):
        key = (photo_reference, max_width)
        if key in image_cache:
            return image_cache[key]
        photo_url = (
            "https://maps.googleapis.com/maps/api/place/photo"
            f"?maxwidth={max_width}&photoreference={photo_reference}"
            f"&key={GOOGLE_PLACES_API_KEY}"
        )
        try:
            response = requests.get(photo_url, stream=True)
            if response.status_code == 200:
                image_data = response.content
                pixmap = QPixmap()
                if pixmap.loadFromData(image_data):
                    image_cache[key] = pixmap
                    return pixmap
        except Exception as e:
            print("Error downloading image:", e)
        return None

# -----------------------------
# Main Application Window
# -----------------------------
class RestaurantFinderWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("GeoGrub")
        self.resize(1280, 800)
        self.worker = None
        self.dark_mode = False

        self.stacked_widget = QStackedWidget()
        self.setCentralWidget(self.stacked_widget)

        self.welcome_page = WelcomePage()
        self.search_page = UpdatedSearchPage()
        self.stacked_widget.addWidget(self.welcome_page)
        self.stacked_widget.addWidget(self.search_page)
        self.stacked_widget.setCurrentWidget(self.welcome_page)

        self.welcome_page.searchInitiated.connect(self.performSearch)
        self.search_page.searchInitiated.connect(self.performSearch)
        self.welcome_page.darkModeToggled.connect(self.setDarkMode)

        self.applyStyle()

    def setDarkMode(self, enabled: bool):
        self.dark_mode = enabled
        self.search_page.setBubbleStyles(self.dark_mode)
        self.applyStyle()
        # Update details widget background explicitly.
        if hasattr(self.search_page, "details_widget"):
            if self.dark_mode:
                self.search_page.details_widget.setStyleSheet("background-color: #23272A;")
            else:
                self.search_page.details_widget.setStyleSheet("background-color: #F0F2F5;")

    def applyStyle(self):
        if self.dark_mode:
            QApplication.instance().setStyleSheet(DARK_STYLE)
        else:
            QApplication.instance().setStyleSheet(LIGHT_STYLE)

    def performSearch(self, location):
        self.search_page.location_input.setText(location)
        self.welcome_page.search_button.setEnabled(False)
        self.search_page.search_button.setEnabled(False)
        self.worker = RestaurantSearchWorker(location)
        self.worker.results_ready.connect(self.handleSearchResults)
        self.worker.error_occurred.connect(self.handleSearchError)
        self.worker.finished.connect(self.searchFinished)
        self.worker.start()

    def handleSearchResults(self, results):
        self.search_page.all_restaurants = results
        self.search_page.restaurant_list.clear()
        for rest in results:
            name = rest.get("name", "Unnamed")
            vicinity = rest.get("vicinity", "No address")
            item_text = f"{name}\n{vicinity}"
            item = QListWidgetItem(item_text)
            item.setData(Qt.UserRole, rest)
            if "photos" in rest and rest["photos"]:
                photo_ref = rest["photos"][0].get("photo_reference")
                pixmap = self.search_page.get_photo_pixmap(photo_ref, max_width=100)
                if pixmap:
                    item.setIcon(QIcon(pixmap))
            self.search_page.restaurant_list.addItem(item)
        if self.search_page.restaurant_list.count() > 0:
            first_item = self.search_page.restaurant_list.item(0)
            self.search_page.restaurant_list.setCurrentItem(first_item)
            self.search_page.onRestaurantClicked(first_item)
        self.stacked_widget.setCurrentWidget(self.search_page)

    def handleSearchError(self, error_msg):
        QMessageBox.critical(self, "Search Error", f"Error during search:\n{error_msg}")

    def searchFinished(self):
        self.welcome_page.stopLoadingAnimation()
        self.search_page.search_button.setEnabled(True)
        self.welcome_page.search_button.setEnabled(True)

if __name__ == "__main__":
    app = QApplication(sys.argv)
    app.setStyle("Fusion")
    QApplication.instance().setStyleSheet(LIGHT_STYLE)
    window = RestaurantFinderWindow()
    window.show()
    sys.exit(app.exec())
