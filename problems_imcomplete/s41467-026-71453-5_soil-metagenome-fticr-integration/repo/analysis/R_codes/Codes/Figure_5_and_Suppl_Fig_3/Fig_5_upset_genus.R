### Upset plot by Young C. Song
### Originally implemented by Emily B. Graham and Izabel Stoher

library(ComplexUpset)
library(dbplyr)
library(tidyverse)
library(rstudioapi)

### The next three lines sets the path to where the code is currently located
this_path <- getActiveDocumentContext()$path
setwd(dirname(this_path))
getwd()

### Read the data table, and convert to binary. Anything greater than or equal to 50 is converted to 1 (present)
### and anything less than 50 is converted to 0 (absent)
data_tbl <- read.csv("./Sample_Data/1000_Soils_drep_MAGs_dbCAN_avg_genus.csv")
row_names <- data_tbl[, 1]
data <- data_tbl[, -1]
row.names(data) <- row_names

binary_data <- as.data.frame(data >= 0.50) * 1

# read metadata
metadata<- read.csv("./Sample_Data/metadata.csv")
row.names(metadata)<-metadata$X
metadata<-metadata[,-1]


# generate data for upset plot
data<- as.data.frame(t(binary_data))
data_upset<- tibble::rownames_to_column(data)
colnames(data_upset)[colnames(data_upset) == "rowname"] <- "sample"
row.names(data_upset)<- data_upset$sample
data_upset<- inner_join(data_upset,metadata)


binary_upset<- function(data, filtervar, starts, location){
  
  binary_df<- filter(data, .data[[filtervar]] == location)
  binary_df<- binary_df[,startsWith(colnames(binary_df), starts)]
  binary_df <- as.numeric(colSums(binary_df) != 0)
  as.vector(binary_df)
}


### This is for combination of layer and resp. level.
create_upset_data_df<- function(data, starts){
  a <- binary_upset(data, "Genus", starts, "g__Methyloceanibacter")
  b <- binary_upset(data, "Genus", starts, "g__Bradyrhizobium")
  c <- binary_upset(data, "Genus", starts, "g__Pseudolabrys")
  d <- binary_upset(data, "Genus", starts, "g__VAZQ01")
  e <- binary_upset(data, "Genus", starts, "g__Udaeobacter")
  f <- binary_upset(data, "Genus", starts, "g__JAFAQB01")
  g <- binary_upset(data, "Genus", starts, "g__Nitrososphaera")
  h <- binary_upset(data, "Genus", starts, "g__TA-21")

  rbind(a, b, c, d, e, f, g, h)
}


upset_plot_data<- create_upset_data_df(data_upset, "CAZy")

run_upset<- function(x,y){
  colnames(x)<- colnames(y)
  x<- as.data.frame(t(x))
  x<- x[rowSums(x)>0,]
  
  upset_location<- as.vector(colnames(x))
  upset(x, upset_location)
}

run_upset(upset_plot_data, data)

#ggsave("./Outputs/Plots/Fig.5_ko_upset_plot.pdf", run_upset(upset_plot_data, data),  
#       width=6, height= 4)
