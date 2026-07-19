#### Implemented by Young C. Song

#load libraries----
library(tidyverse)
library(NOISeq)
library(dplyr)
library(reshape2)

library(rstudioapi)

### The next three lines sets the path to where the code is currently located
this_path <- getActiveDocumentContext()$path
setwd(dirname(this_path))
getwd()

#load data----

#load/transform metadata 

ko_path_tbl <- read.delim("./Sample_Data/1000_Soils_drep_selected_MAGs_KO_mapped_aa.tsv", stringsAsFactors = FALSE, header=TRUE, check.names=FALSE)

### We are going to remove some rows (or KOs) that either have zeroes across the samples or
### are just present in very low level

# First, calculate the averages of each row across the samples
ko_path_tbl$average <- rowMeans(ko_path_tbl[, 2:(ncol(ko_path_tbl))])

ko_path_tbl_sort_avg <- ko_path_tbl[order(ko_path_tbl$average, decreasing = TRUE), ]

# This finds the threshold index, where the sum of the averages
# on the left side of it would represent 95% of the total sum of the averages
# Codes for drawing the threshold is currently commented out.
total_avg_sum <- sum(ko_path_tbl_sort_avg$average)
cumul_avg_sum <- cumsum(ko_path_tbl_sort_avg$average)

threshold_row <- which(cumul_avg_sum >= 0.95 * total_avg_sum)[1]
threshold_row
threshold_value <- ko_path_tbl_sort_avg$average[threshold_row]
threshold_value

# Draw a bar chart of averages and draw a red line to indicate the point
# where left side of it represents 95% of the cumulative sum of averages.
ggplot(ko_path_tbl_sort_avg, aes(x = reorder(KO_Gene_Name, -average), y = average)) +
  geom_col() +  # Create bar chart
  geom_vline(
    xintercept = which(ko_path_tbl_sort_avg$average == ko_path_tbl_sort_avg$average[threshold_row]),  # Add a red vertical line
    linetype = "dashed", color = "red", linewidth = 0.3
  ) +
  labs(
    title = "Histogram of Averages with Threshold Highlighted",
    x = "KO_Gene_Name",
    y = "Average raw count"
  ) +
  theme_minimal() +
  theme(
    axis.text.x = element_text(size = 7, angle = 45, hjust = 1)
  )

ko_path_tbl_row_filtered <- ko_path_tbl_sort_avg[ko_path_tbl_sort_avg$average >= threshold_value,]
write.table(ko_path_tbl_row_filtered, "./Sample_Data/1000_Soils_drep_sel_MAGs_KO_filter_map.tsv", sep = "\t", row.names = FALSE, quote = FALSE)

### Calculate the average of each KO for each genus
### Read the tables
### Map KOs in 1000_Soils_drep_select_MAGs_KO_mapped_aa_filtered.tsv to pathway
### then order the rows based on pathway.
ko_genome_table <- read.delim("./Sample_Data/1000_Soils_drep_sel_MAGs_KO_filter_map.tsv", stringsAsFactors = FALSE, check.names=FALSE)
genome_genus_table <- read.delim("./Sample_Data/genome_genus_table.tsv", stringsAsFactors = FALSE)

# Extract and preserve the original KO_Gene_Name order as a character vector
ko_gene_name_order <- as.character(ko_genome_table$KO_Gene_Name)

# Reshape the KO table to long format
ko_genome_long <- ko_genome_table %>%
  pivot_longer(cols = -KO_Gene_Name, names_to = "Genome", values_to = "Value") %>%
  mutate(KO_Gene_Name = as.character(KO_Gene_Name)) # Ensure KO_Gene_Name is a plain string

# Preserve the order of Genus from genome_genus_table
genome_genus_table <- genome_genus_table %>%
  rename(Genus = Genus) %>% # Rename genus_level to Genus
  mutate(Genus = factor(Genus, levels = unique(Genus))) # Ensure Genus order is kept intact

# Merge genus information into the reshaped KO_Gene_Name data
merged_data <- ko_genome_long %>%
  left_join(genome_genus_table, by = c("Genome" = "Genome"))

# Calculate the average of each KO_Gene_Name for each Genus
average_ko_genus <- merged_data %>%
  group_by(KO_Gene_Name, Genus) %>%
  summarize(Average = mean(Value, na.rm = TRUE), .groups = "drop")

# Force KO_Gene_Name to follow original order, ensuring consistent formatting and order
average_ko_genus <- average_ko_genus %>%
  mutate(
    KO_Gene_Name = factor(KO_Gene_Name, levels = ko_gene_name_order), # Apply order from the original input file
    Genus = factor(Genus, levels = unique(genome_genus_table$Genus))  # Preserve Genus order
  )

# Debugging: Ensure correct order of KO_Gene_Name
print("Levels of KO_Gene_Name:")
print(levels(average_ko_genus$KO_Gene_Name))

# Save the ordered average table to verify
write.table(average_ko_genus, file = "./Sample_Data/ordered_average_ko_gene_name_by_genus.tsv", sep = "\t", row.names = FALSE, quote = FALSE)

# Create a bubble plot with reverse Y-axis
bubble_plot <- ggplot(average_ko_genus, aes(x = Genus, y = KO_Gene_Name, size = Average)) +
  geom_point(alpha = 0.7) +
  scale_size_continuous(name = "Average Value") +
  scale_y_discrete(limits = rev(levels(average_ko_genus$KO_Gene_Name))) + # Reverse the Y-axis order
  labs(x = "Genus", y = "KO Gene Name") +
  theme_minimal() +
  theme(axis.text.x = element_text(angle = 45, hjust = 1))  # Ensure readability of labels

# Debugging: Ensure Y-axis reflects the order of KO_Gene_Name
bubble_plot <- bubble_plot +
  scale_y_discrete(limits = ko_gene_name_order) # Explicitly set the Y-axis order to the original KO_Gene_Name order

print(bubble_plot)

