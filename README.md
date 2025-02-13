# Food Finder

Food Finder is a standalone Python application that allows users to search for nearby restaurants by entering a location (such as a zip code or city name) or by using IP-based geolocation for a "Find Restaurants Near Me" feature. The application displays restaurant details, including images, address, contact information, ratings, and reviews—all within a modern, responsive GUI built with PySide6.

## Features

- **Search by Location:**  
  Users can enter a zip code or city name to search for restaurants in the vicinity.

- **Find Restaurants Near Me:**  
  Uses IP-based geolocation (via the `geocoder` library) to determine the user's approximate location and list nearby restaurants.

- **Random Restaurant Selection:**  
  Offers a "Select Random Restaurant" feature that randomly picks a restaurant from the search results. Try it when you're not sure where you want to go!

- **Detailed Restaurant Information:**  
  Displays comprehensive details for each restaurant, including:
  - Name
  - Address (with a clickable link to Google Maps)
  - Phone number
  - Rating and reviews
  - Website URL
  - Price level

- **Image Gallery:**  
  Shows restaurant images within a fixed container with left/right arrow buttons to cycle through multiple photos (if available). Images are scaled uniformly without warping.

- **Dark Mode:**  
  A dark mode toggle is available to switch between light and dark themes for viewing in different lighting conditions or if you don't want to burn your eyes.

- **Modern and Responsive GUI:**  
  Built using PySide6.

## How It Works

1. **Data Source:**  
   Food Finder leverages the Google Places API to retrieve restaurant data based on the user's input (zip code, city name, or geolocation coordinates).

2. **Geolocation:**  
   The "Find Restaurants Near Me" feature uses the `geocoder` library to determine the user's approximate location from their IP address.

3. **User Interface:**  
   The GUI is constructed with PySide6:
   - **Welcome Page:**  
     Features the application title, subtitle, a centered search bar, and buttons for "Search" and "Find Restaurants Near Me." The dark mode toggle is located on the right.
   - **Main Application Page:**  
     Displays search results on the side and a detailed view of the selected restaurant, including the restaurant name, image gallery (with cycling arrows), address, and reviews.

4. **Image Handling:**  
   Restaurant images are downloaded from the Google Places API and cached. The images are then scaled to fit a fixed-size container so that the layout remains consistent regardless of the image's original dimensions.

## Requirements

- Python 3.8 or later
- [PySide6](https://pypi.org/project/PySide6/)
- [Requests](https://pypi.org/project/requests/)
- [Geopy](https://pypi.org/project/geopy/)
- [Geocoder](https://pypi.org/project/geocoder/)

## Installation

1. **Clone the Repository:**

   ```bash
   git clone https://github.com/jjjohnywaffles/foodfinder.git
   cd foodfinder

2. **Install Dependencies:**
    pip install -r requirements.txt

3. **Set Up the API Key:**
    Replace the API key variable with your own API key or use the .exe file directly.

4. **Run the Application:**
    python foodfinder.py

    Alternatively you can download the .exe file which is directly compiled from this code. 