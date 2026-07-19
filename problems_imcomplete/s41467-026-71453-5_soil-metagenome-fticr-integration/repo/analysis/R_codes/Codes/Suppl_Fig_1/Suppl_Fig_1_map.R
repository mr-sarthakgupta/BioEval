## Suppl_Fig_1_map.R
## By Young C. Song
## This script generates the map of the 1000 Soils samples sites shown
## in Supplementary Figure 1.

library(sf)
library(ggplot2)
library(readr)
library(rnaturalearth)
library(rnaturalearthdata)
library(dplyr)
library(rstudioapi)

### The next three lines sets the path to where the code is currently located
this_path <- getActiveDocumentContext()$path
setwd(dirname(this_path))
getwd()

# Read your CSV file
# Replace "your_file.csv" with the actual path to your CSV file
data <- read_csv("./Sample_Data/1000_Soil_Sites.csv")

# Check the structure of your data
print(head(data))
print(colnames(data))

# Get US states data
us_states <- ne_states(country = "united states of america", returnclass = "sf")

# Filter to get only continental US states (optional - removes Alaska, Hawaii, territories)
# Comment out 23 and 24 and change the data to us_states in line 35 if you want to include Alaska and Hawaii
continental_us <- us_states %>%
  filter(!name %in% c("Alaska", "Hawaii"))

# Convert your data to sf object
# Make sure longitude and latitude columns exist and have the right names
data_sf <- st_as_sf(data, 
                    coords = c("Longitude", "Latitude"), 
                    crs = 4326)

# Create the map
map_plot <- ggplot() +
  # Add US states
  geom_sf(data = continental_us, 
          fill = "white", 
          color = "gray50", 
          size = 0.3) +
  # Add sample points
  geom_sf(data = data_sf, 
          aes(color = Sample_Type), 
          size = 3, 
          alpha = 0.8) +
  # Add labels for sample names
  geom_sf_text(data = data_sf,
               aes(label = Sample),
               size = 3,
               nudge_x = 0.5,  # Offset text slightly to avoid overlap with points
               nudge_y = 0.5,
               check_overlap = TRUE) +  # Prevents overlapping labels
  # Set coordinate system and limits for continental US
  coord_sf(xlim = c(-125, -66), 
           ylim = c(20, 50), 
           crs = st_crs(4326)) +
  # Customize appearance
  labs(title = "Sample Locations by Type",
       subtitle = "United States",
       color = "Sample Type",
       caption = "Data: Your Sample Data") +
  theme_void() +  # Clean map theme
  theme(
    plot.title = element_text(hjust = 0.5, size = 16, face = "bold"),
    plot.subtitle = element_text(hjust = 0.5, size = 12),
    legend.position = "bottom",
    legend.title = element_text(size = 12, face = "bold"),
    panel.background = element_rect(fill = "aliceblue"),
    plot.background = element_rect(fill = "white")
  ) +
  # Optional: customize colors
  scale_color_brewer(type = "qual", palette = "Set1")

# Display the map
print(map_plot)





