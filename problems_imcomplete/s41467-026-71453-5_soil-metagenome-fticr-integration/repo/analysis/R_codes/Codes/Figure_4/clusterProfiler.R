#### Note: This script is a modified version of the script originally
#### written by Linnea Hernandez. It incorporates clusterProfiler package that 
#### includes the function enrichKEGG used to generate a table of corrected p-values
#### that was subsequently used in other script to generate Figure 4.

library(clusterProfiler)
library(dplyr)
library(DOSE)
library(enrichplot)
library(tidyr)
library(rstudioapi)

### The next three lines sets the path to where the code is currently located
this_path <- getActiveDocumentContext()$path
setwd(dirname(this_path))
getwd()

data <- read.csv("./Sample_Data/fticr_ko_50pct.csv", header = TRUE)


#### Pull the subset of input data for surface/high
data.TH <- data %>%
  filter(Partition == "TOP_High")

#### Pull the subset of input data for surface/low
data.TL <- data %>%
  filter(Partition == "TOP_Low")

#### Pull the subset of input data for subsoil/high
data.BH <- data %>%
  filter(Partition == "BTM_High")

#### Pull the subset of input data for subsoil/low
data.BL <- data %>%
  filter(Partition == "BTM_Low")

#### Extract only list of KOs
ko.TH <- data.TH$KO
ko.TL <- data.TL$KO
ko.BH <- data.BH$KO
ko.BL <- data.BL$KO

#### KEGG pathway over-representation analysis
k.path.TH <- enrichKEGG(gene = ko.TH,
                        organism = 'ko',
                        pvalueCutoff = 0.05)

k.path.TL <- enrichKEGG(gene = ko.TL,
                        organism = 'ko',
                        pvalueCutoff = 0.05)

k.path.BH <- enrichKEGG(gene = ko.BH,
                        organism = 'ko',
                        pvalueCutoff = 0.05)

k.path.BL <- enrichKEGG(gene = ko.BL,
                        organism = 'ko',
                        pvalueCutoff = 0.05)

#### Select the columns you want, keeping them as data frames
k.path.TH.data <- k.path.TH[, c("Description", "GeneRatio", "p.adjust")]
k.path.TL.data <- k.path.TL[, c("Description", "GeneRatio", "p.adjust")]
k.path.BH.data <- k.path.BH[, c("Description", "GeneRatio", "p.adjust")]
k.path.BL.data <- k.path.BL[, c("Description", "GeneRatio", "p.adjust")]

#### Add Coordinate column
k.path.TH.data$Coordinate <- 1
k.path.TL.data$Coordinate <- 2
k.path.BH.data$Coordinate <- 3
k.path.BL.data$Coordinate <- 4

#### Helper to map p.adjust to P_value_code
categorize_p <- function(p) {
  cut(
    p,
    breaks = c(-Inf, 1e-20, 1e-15, 1e-10, 1e-5, 1e-3, Inf),
    labels = c("E", "A", "D", "C", "B", "F"),
    right  = FALSE  # [lower, upper)
  )
}

#### Add P_value_code column to each table
k.path.TH.data$P_value_code <- categorize_p(k.path.TH.data$p.adjust)
k.path.TL.data$P_value_code <- categorize_p(k.path.TL.data$p.adjust)
k.path.BH.data$P_value_code <- categorize_p(k.path.BH.data$p.adjust)
k.path.BL.data$P_value_code <- categorize_p(k.path.BL.data$p.adjust)

#### Helper: convert "A/B" to A/B as numeric
ratio_to_numeric <- function(x) {
  x <- as.character(x)
  parts <- strsplit(x, "/")
  num   <- as.numeric(sapply(parts, `[`, 1))
  den   <- as.numeric(sapply(parts, `[`, 2))
  num / den
}

#### Apply to each table
k.path.TH.data$GeneRatio <- ratio_to_numeric(k.path.TH.data$GeneRatio)
k.path.TL.data$GeneRatio <- ratio_to_numeric(k.path.TL.data$GeneRatio)
k.path.BH.data$GeneRatio <- ratio_to_numeric(k.path.BH.data$GeneRatio)
k.path.BL.data$GeneRatio <- ratio_to_numeric(k.path.BL.data$GeneRatio)


#### Merge the tables into one by first renaming some columns and adding an additional 
#### "PathCode" column (numerical values defining a unique pathways in the data.)

#### Rename columns in each table to a common set
rename_cols <- function(df) {
  df2 <- df[, c("Description", "Coordinate", "GeneRatio", "p.adjust", "P_value_code")]
  names(df2) <- c("Pathway", "Coordinate", "GeneRatio", "P_value", "P_value_code")
  df2
}

k.path.TH.data2 <- rename_cols(k.path.TH.data)
k.path.TL.data2 <- rename_cols(k.path.TL.data)
k.path.BH.data2 <- rename_cols(k.path.BH.data)
k.path.BL.data2 <- rename_cols(k.path.BL.data)

#### 2. Concatenate (row‑bind) the four tables. Then filter the rows such that
### we keep the pathways present in 2 or more soil types

merged_tbl <- rbind(
  k.path.TH.data2,
  k.path.TL.data2,
  k.path.BH.data2,
  k.path.BL.data2
)

#### the filter part
path_counts <- merged_tbl %>%
  distinct(Pathway, Coordinate) %>%         # unique (Pathway, Coordinate) pairs
  count(Pathway, name = "n_tables") 

merged_filtered <- merged_tbl %>%
  inner_join(path_counts, by = "Pathway") %>%
  filter(n_tables >= 2) %>%
  filter(!if_all(everything(), is.na)) %>%
  select(-n_tables)


#### 3. Sort by Pathway (alphanumeric)

merged_filtered <- merged_filtered[order(merged_filtered$Pathway), ]

#### 4. Create PathCode: same code for identical Pathway names

merged_filtered$PathCode <- as.numeric(factor(merged_filtered$Pathway, levels = unique(merged_filtered$Pathway)))

write.table(merged_filtered, file="./Sample_Data/FTICR_KO_50_pct.tsv", sep="\t", row.names=FALSE, quote=FALSE)
