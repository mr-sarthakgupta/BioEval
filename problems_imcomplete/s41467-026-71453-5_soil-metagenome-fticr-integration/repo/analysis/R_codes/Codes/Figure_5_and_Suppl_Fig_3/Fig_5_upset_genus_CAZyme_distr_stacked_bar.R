### This script will generate stacked bar charts in Figure 5

### Load necessary libraries
library(ggplot2)
library(dplyr)
library(rstudioapi)

this_path <- getActiveDocumentContext()$path
setwd(dirname(this_path))
getwd()


# Read the tab-separated file into R
data <- read.delim("./Sample_Data/1000_Soils_drep_MAGs_CAZy_cat_assign.tsv", header = TRUE, stringsAsFactors = FALSE)

# Extract the CAZy prefix from the first column (the CAZy ID)
data$CAZy_Category <- sub("^(AA|CBM|CE|GT|GH|PL).*", "\\1", data[, 1])

# Step 1: Count the instances of CAZy ID strings for each group
category_counts <- data %>%
  group_by(Group = data[, 2], CAZy_Category) %>%
  tally(name = "Count")

# Step 2: Calculate the relative distribution within each group
category_distribution <- category_counts %>%
  group_by(Group) %>%
  mutate(Relative_Distribution = (Count / sum(Count)) * 100)


# Save raw counts as a TSV file
raw_counts <- category_counts %>%
  pivot_wider(names_from = CAZy_Category, values_from = Count, values_fill = 0)  # Fill missing categories with 0

write.table(raw_counts, "./Sample_Data/1000_Soils_drep_MAGs_CAZy_cat_raw_counts.tsv", sep = "\t", row.names = FALSE, quote = FALSE)

# Save relative distributions as a TSV file
relative_distributions <- category_distribution %>%
  select(Group, CAZy_Category, Relative_Distribution) %>%
  pivot_wider(names_from = CAZy_Category, values_from = Relative_Distribution, values_fill = 0)  # Fill missing categories with 0

write.table(relative_distributions, "./Sample_Data/1000_Soils_drep_MAGs_CAZy_cat_rel_distr.tsv", sep = "\t", row.names = FALSE, quote = FALSE)


# Step 3: Draw a stacked bar chart using the relative distribution
ggplot(category_distribution, aes(x = Group, y = Relative_Distribution, fill = CAZy_Category)) +
  geom_bar(stat = "identity") +
  labs(title = "Relative Distribution of CAZy Categories Across Groups",
       x = "Group",
       y = "Relative Distribution (%)") +
  theme_minimal()

# Save the plot to file (optional)
ggsave("stacked_bar_chart.png", width = 8, height = 6)