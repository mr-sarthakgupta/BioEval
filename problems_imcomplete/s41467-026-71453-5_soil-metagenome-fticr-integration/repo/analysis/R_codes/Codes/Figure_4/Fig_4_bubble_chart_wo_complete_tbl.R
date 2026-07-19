### Figure_4_bubble_chart_wo_complete_tbl.R
### By Young C. Song
### This script generates bubble and bar plots shown in Figure 4.
### Before running this code, run clusterProfiler.R to generate the input table.

library(RColorBrewer)
library(ggplot2)
library(reshape)
library(dplyr)
library(rstudioapi)

### The next three lines sets the path to where the code is currently located
this_path <- getActiveDocumentContext()$path
setwd(dirname(this_path))
getwd()

#### Everything up to line 25 generates the bubble chart ####

bubble_tbl <- read.table("./Sample_Data/FTICR_KO_50_pct.tsv",header=TRUE,sep="\t")

# Build a named vector: names are codes, values are pathway labels
code2label <- bubble_tbl %>%
  distinct(PathCode, Pathway) %>%      # one row per code
  arrange(PathCode) %>%
  { setNames(.$Pathway, .$PathCode) }

ggplot(bubble_tbl, aes(x = Coordinate, y = PathCode)) +
  geom_point(aes(color = P_value_code, size = GeneRatio), alpha = 0.5) +
  scale_y_reverse(                              # smallest code on top
    breaks = sort(unique(bubble_tbl$PathCode)), # positions
    labels = code2label[as.character(sort(unique(bubble_tbl$PathCode)))]
  ) +
  scale_color_manual(values = c("#240D43", "#327ECA", "#63D0F0",
                                "#F3EDBF", "#E7A374", "#D6681B")) +
  theme_bw() +
  theme(legend.position = "bottom")

#### Bar Plot ####

bar_tbl <- read.csv("./Sample_Data/FTICR_KO_50_pct_num_KOs.csv")

data <- data.frame(
  name=bar_tbl$Variable,
  value=bar_tbl$Value
)

ggplot(data, aes(x=name, y=value)) + geom_bar(stat="identity", width=0.7) + 
  theme(text=element_text(size=5)) +
  coord_flip()



