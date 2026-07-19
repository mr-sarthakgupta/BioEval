### Figure_1_heatmap_geom_tile_bar.R
### By Young C. Song
### This script generates heatmap and bar plots shown
### in Figure 1.

library(RColorBrewer)
library(ggplot2)
library(reshape)
library(rstudioapi)

### Everything upto line 34 will generate the heatmap portion.
### The next three lines sets the path to where the code is currently located
this_path <- getActiveDocumentContext()$path
setwd(dirname(this_path))
getwd()

coul <- brewer.pal(5, "Greys")

heatmap_tbl <- read.csv("./Sample_Data/1000_Soils_drep_MAGs_row_col_cmp.csv")

### change the data structure of the table to be
### compatible with ggplot
df <- melt(heatmap_tbl)
colnames(df) <- c("x", "y", "value")

### geom_tile is for borders
### theme controls text size and orientation
### in scale_fill_gradientn, trans controls the direction of the gradient
### coord_fixed draws the heatmap in square tiles

ggplot(df, aes(x = x, y = y, fill = value)) +
  geom_tile(color="white",lwd=0.5,linetype=1) +
  theme(text=element_text(size=5),axis.text.x=element_text(angle=90,hjust=1)) + 
  scale_fill_gradientn(colors=hcl.colors(10,"Grays"),trans="reverse") + coord_fixed()

#### Bar Plot ####

bar_tbl <- read.csv("./Sample_Data/1000_Soils_drep_MAGs_classify_genus_ct.csv",header=TRUE)
bar_tbl$variable <- factor(bar_tbl$variable, levels=rev(bar_tbl$variable))

ggplot(bar_tbl, aes(x=variable, y=value)) + 
  geom_bar(stat="identity", width=0.7) + 
  theme(text=element_text(size=5)) +
  coord_flip()


