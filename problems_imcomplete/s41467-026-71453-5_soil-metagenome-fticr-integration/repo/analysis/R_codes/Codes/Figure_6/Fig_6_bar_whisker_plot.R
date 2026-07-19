### Bar Whisker Plot by Young C Song
### This script reads the abundance of each elements (rows) across the samples/species (columns)
### and generates bar and whisker plot for each element.
### Only the elements that are present across 3 or more samples/species are presented
### in the final figure.

# Load necessary libraries
library(ggplot2)
library(dplyr)
library(tidyr)
library(viridis)
library(hrbrthemes)

library(rstudioapi)

### The next three lines sets the path to where the code is currently located
this_path <- getActiveDocumentContext()$path
setwd(dirname(this_path))
getwd()

# Load the tab-separated table
data <- read.table("./Sample_Data/1000_Soils_drep_MAGs_genus_fba_aa_uptake_ln_corr.tsv", header = TRUE, sep = "\t", check.names=FALSE, stringsAsFactors = FALSE)

# Melt the data into a long format for filtering (this assumes the first column contains compounds)
data_long <- pivot_longer(data, cols = -Compound, names_to = "Lineage", values_to = "Uptake")

# Filter rows: keep only compounds present in three or more lineages (non-zero uptake values)
filtered_data <- data_long %>%
  group_by(Compound) %>%
  filter(sum(Uptake > 0) >= 3) %>%
  ungroup()


plot <- ggplot(filtered_data, aes(x = Compound, y = Uptake)) +
  geom_boxplot(outlier.size = 0.5, fill = "lightblue", alpha = 0.5) +  # Draw one box-per-compound
  geom_jitter(aes(color = Lineage), size = 3, width = 0.2, alpha = 0.8) +  # Add jittered points for lineages
  theme_minimal() +
  labs(
    title = "Compound Uptake Across Genus-Level Lineages",
    x = "Compound",
    y = "Uptake",
    color = "Lineage"
  ) +
  theme(
    axis.text.x = element_text(angle = 45, hjust = 1),  # Rotate x-axis labels for readability
    legend.position = "bottom"
  )
# Save the plot as an image file
ggsave("boxplot_compound_uptake.png", plot, width = 10, height = 6, dpi = 300)

# Print the plot in the console
print(plot)