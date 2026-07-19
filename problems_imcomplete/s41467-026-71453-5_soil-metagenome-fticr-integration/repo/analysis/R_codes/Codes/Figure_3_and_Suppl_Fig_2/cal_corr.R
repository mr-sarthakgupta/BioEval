#### cal_corr.R by Young C. Song (11/05/24)
#### calculates correlation between abundance of KO (or taxonomic groups) AND ICR binary values
#### based on code by EBGraham (accessed on the same day as implementation date)
####
#### Note: This script does NOT generate any visualizations. It will generate the correlation matrix, which can be filtered
#### using specific set of parameters. The resulting file then can be imported to Cytoscape to generate the network figures.
####
#### Also Note: If you do not have sufficient memory to flatten correlation matrix, use the following codes
#### > library(usethis) 
#### > usethis::edit_r_environ()
#### Include the following line: R_MAX_VSIZE=100Gb
#### Save the .Renviron and them re-start R session.

rm(list=ls());graphics.off()
library(Hmisc)
library(dplyr)
library(tidyverse)
library(NOISeq)
library(reshape2)
library(rstudioapi)

### The next three lines sets the path to where the code is currently located
this_path <- getActiveDocumentContext()$path
setwd(dirname(this_path))
getwd()

#####function for flattening correlation matrix####
# ++++++++++++++++++++++++++++
# flattenCorrMatrix
# ++++++++++++++++++++++++++++
# cormat : matrix of the correlation coefficients
# pmat : matrix of the correlation p-values
flattenCorrMatrix <- function(cormat, pmat) {
  ut <- upper.tri(cormat)
  data.frame(
    row = rownames(cormat)[row(cormat)[ut]],
    column = rownames(cormat)[col(cormat)[ut]],
    cor  =(cormat)[ut],
    p = pmat[ut]
  )
}


####load in data####
ko.table <- read.delim("./Sample_Data/1000_Soils_drepd_subsoil_low_KO.tsv", stringsAsFactors = FALSE, header=TRUE, row.names=1, check.names=FALSE)
icr.table <- read.csv('./Sample_Data/1000_Soils_FTICR_subsoil_low_filtered.csv', stringsAsFactors = FALSE, header = T, row.names = 1, check.names = FALSE)

#### We are going to do pre-processing of the KO data.
#### Because the MAGs have been generated via coassembly and co-binning (refer to Bin Chicken manual),
#### some of the MAGs names will reflect this process (especially at the 'iterate')
#### process (e.g., itr_1..., itr_2...). We are first going to remove these columns, as
#### they are not specific to the samples.
#### We are then going to add/collapse the columns that share the same sample name.

# Step 1: Remove the "itr" columns
ko.table.itr.remove <- ko.table[, !grepl("^itr", colnames(ko.table))]

# Step 2: Collapse columns based on shared substrings (prefix) and sum their values across rows.
# Extract the prefix from the column names before the first "-"

#column_prefix <- sub("_.*", "", colnames(ko.table.itr.remove))  # Extract prefix while keeping "-TOP" or "-BTM"
ko.table.collapsed <- as.data.frame(ko.table.itr.remove) %>% 
  as_tibble(rownames = "KO") %>%  # Convert to tibble and preserve KO IDs
  pivot_longer(cols = -KO, names_to = "Sample", values_to = "Value") %>%  # Reshape to long format
  mutate(Prefix = sub("_.*", "", Sample)) %>%  # Extract the prefix while keeping "-TOP" or "-BTM"
  group_by(KO, Prefix) %>%  # Group by KO and Prefix
  summarise(Summed_Value = sum(Value), .groups = "drop") %>%  # Sum values within grouped columns
  pivot_wider(names_from = Prefix, values_from = Summed_Value)  # Reshape back to wide format

#### End of the pre-processing step

#### We are now going to filter the rows (i.e., KOs). This is done by first calculating the average
#### of the KOs across the column. We then draw a curve (or barchart) of the averages. 
#### The KOs that make up the 95% of the total sum of the averages are retained, while everything else
#### is removed.

ko.table.collapsed$average <- rowMeans(ko.table.collapsed[, 2:(ncol(ko.table.collapsed))])

ko_path_tbl_sort_avg <- ko.table.collapsed[order(ko.table.collapsed$average, decreasing = TRUE), ]

# This finds the threshold index, where the sum of the averages
# on the left side of it would represent 95% of the total sum of the averages
# Codes for drawing the threshold is currently commented out.
total_avg_sum <- sum(ko_path_tbl_sort_avg$average)
cumul_avg_sum <- cumsum(ko_path_tbl_sort_avg$average)

threshold_row <- which(cumul_avg_sum >= 0.95 * total_avg_sum)[1]
threshold_row
threshold_value <- ko_path_tbl_sort_avg$average[threshold_row]
threshold_value

#### This segment (up to line 99) is optional. It basically draws the "curve" with
#### a threshold point. Anything left of the threshold is kept.
ggplot(ko_path_tbl_sort_avg, aes(x = reorder(KO, -average), y = average)) +
  geom_col() +  # Create bar chart
  geom_vline(
    xintercept = which(ko_path_tbl_sort_avg$average == ko_path_tbl_sort_avg$average[threshold_row]),  # Add a red vertical line
    linetype = "dashed", color = "red", linewidth = 0.3
  ) +
  labs(
    title = "Histogram of Averages with Threshold Highlighted",
    x = "KO",
    y = "Average raw count"
  ) +
  theme_minimal() +
  theme(
    axis.text.x = element_text(size = 7, angle = 45, hjust = 1)
  )

ko_path_tbl_row_filtered <- ko_path_tbl_sort_avg[ko_path_tbl_sort_avg$average >= threshold_value,]
write.table(ko_path_tbl_row_filtered, "./by_layer_respiration/ko_filtered/1000_Soils_drepd_subsoil_low_KO_filtered.tsv", sep = "\t", row.names = TRUE, quote = FALSE)
#### End of the KO filtering section

#### The following section ensures the consistency between the KO and the ICR data frames
# Step 1: Create data frame for KO table, after transpose
ko_path_tbl_row_filtered <- ko_path_tbl_row_filtered[, !colnames(ko_path_tbl_row_filtered) %in% "average"] # remove the average column

ko.table.tr <- t(as.data.frame(ko_path_tbl_row_filtered))

colnames(ko.table.tr) <- as.character(unlist(ko.table.tr[1, ]))  
ko.table.tr <- ko.table.tr[-1, ]
ko.table.tr <- as.data.frame(ko.table.tr)

# Step 2: Create data frame for ICR table, after transpose
icr.table.tr=as.data.frame(t(icr.table))

# Step 3: Make sure both data frames have the same set of rows.

common_rows <- intersect(rownames(ko.table.tr), rownames(icr.table.tr))

# Subset both data frames to keep only the common rows
ko.table.tr_common  <- ko.table.tr[common_rows, , drop = FALSE]
icr.table.tr_common <- icr.table.tr[common_rows, , drop = FALSE]

# Step 4:check if the row names between the two transformed tables are in the correct order
row.names(ko.table.tr_common) == row.names(icr.table.tr_common)

ko.table.tr <- ko.table.tr_common
icr.table.tr <- icr.table.tr_common
#### End of the data consistancy check

###### spearman correlation, between ko and icr #####
ko.cor  = ko.table.tr
icr.cor = icr.table.tr #create for use below

#add "ko" or "icr" to names to distinguish KO columns vs ICR columns
names(ko.cor) = paste0("ko.",names(ko.cor))
names(icr.cor) = paste0("icr.",names(icr.cor))

#drop the variables (columns) occurring in less than 3 samples in icr matrices
icr.num2 = apply(icr.cor,2, function(x) length(which(x>0))) #number of samples each ICR is in
#ko.num2 = apply(ko.cor,2, function(x) length(which(x>0))) #number of samples each KO is in

ind.rm = unique(c(which(icr.num2<3))) #columns to remove

# Use the values generated from line 51 to filter the ICR table (KO table has already gone through filtering process).
# Keep in mind, rows in each table are the samples, and the columns are the variables
# We are filtering the columns, not rows
#ko.cor.filt = ko.cor[,-ind.rm]
icr.cor.filt = icr.cor[,-ind.rm]

# check if the row names between the two transformed tables are in the correct order
#row.names(ko.cor.filt) == row.names(icr.cor.filt)
row.names(ko.cor) == row.names(icr.cor.filt)

#combine KO and ICR into one matrix
ko.icr.combine = cbind(ko.cor,icr.cor.filt)
dim(ko.icr.combine) # Dimension of the combined matrix
ncol(ko.cor);ncol(icr.cor.filt) # Another sanity check. Add these two together and we should get the column number from the previous row


# The real deal: Calculate the Speaman matrix. This could take a while. 
cor.mat = rcorr(as.matrix(ko.icr.combine),type = "spearman")

#write out stats from correlation matrices
#write.csv(cor.mat$r,"./corr_matrix_stats/ko_vs_icr/full_r.csv")
#write.csv(cor.mat$P,"./corr_matrix_stats/ko_vs_icr/full_P.csv")
#write.csv(cor.mat$n,"./corr_matrix_stats/ko_vs_icr/full_n.csv")

write.csv(cor.mat$r,"./corr_matrix_stats/ko_vs_icr/by_layer_resp/1000_Soils_drep_MAGs_ICR_subsoil_low_r.csv")
write.csv(cor.mat$P,"./corr_matrix_stats/ko_vs_icr/by_layer_resp/1000_Soils_drep_MAGs_ICR_subsoil_low_P.csv")
write.csv(cor.mat$n,"./corr_matrix_stats/ko_vs_icr/by_layer_resp/1000_Soils_drep_MAGs_ICR_subsoil_low_n.csv")

#####flatten matrix######
flat.cor.mat = flattenCorrMatrix(cor.mat$r, cor.mat$P)
#write.csv(flat.cor.mat,"./corr_matrix_stats/ko_vs_icr/full_flat_stats.csv",row.names = F)
write.csv(flat.cor.mat,"./corr_matrix_stats/ko_vs_icr/by_layer_resp/1000_Soils_drep_MAGs_ICR_subsoil_low_full_stats.csv",row.names = F)


###optional: remove ko-ko and icr-icr correlations
###in case of ko-ko, it might be worth a while keeping them, as they may represent pathways
###so for now, we only remove icr-icr correlations

#### Comment or un-comment the line below as you see fit. This is to prevent from building
#### the table from scratch.
#flat.cor.mat=read.csv("./corr_matrix_stats/ko_vs_icr/full_flat_stats.csv",header = T)
flat.cor.mat=read.csv("./corr_matrix_stats/ko_vs_icr/by_layer_resp/1000_Soils_drep_MAGs_ICR_subsoil_low_full_stats.csv",header = T)

#### We are going to remove the rows that are affiliated with ICR-ICR or KO-KO
#### relationships
ind.icr1 = grep("icr",flat.cor.mat[,1])#finds "icr" in col 1
ind.icr2 = grep("icr",flat.cor.mat[,2])#finds "icr" in col 2

ind.icr = match(ind.icr1,ind.icr2)

#sanity check: check matching
ind.icr1[1:3];ind.icr2[ind.icr[1:3]]
ind.icr1[101:103];ind.icr2[ind.icr[101:103]]
ind.icr.rm = ind.icr2[ind.icr]#index of icr-icr pairs to remove

# (Added on 11.07.24) Looking at the preliminary results,
# we also remove the ko-ko correlations as well. We may lose some information, 
# but the pathway to metabolite relationship for most part should be intact.

ind.ko1 = grep("ko",flat.cor.mat[,1])#finds "ko" in col 1
ind.ko2 = grep("ko",flat.cor.mat[,2])#finds "ko" in col 2

ind.ko = match(ind.ko1,ind.ko2)

#sanity check: check matching
ind.ko1[1:3];ind.ko2[ind.icr[1:3]]
ind.ko1[101:103];ind.ko2[ind.icr[101:103]]
ind.ko.rm = ind.ko2[ind.ko]#index of ko-ko pairs to remove



# Remove the rows from the flatttend corr. matrix where we have
# ICR-ICR or KO-KO relationship.
ind = c(ind.icr.rm,ind.ko.rm)
isna=ind[is.na(ind)==T] # it doesn't appear that there is any "NA" in the indices. So commenting out this one and the one below
ind = ind[-which(is.na(ind)==T)]
flat.cor.mat.icr.ko.rm = flat.cor.mat[-ind,]

# check to see if icr-icr correlation have been removed
#ind.icr1.check = grep("icr",flat.cor.mat.icr.ko.rm[,1])
#ind.icr2.check = grep("icr",flat.cor.mat.icr.ko.rm[,2])#finds "icr" in col 2

#ind.icr.check = match(ind.icr1.check,ind.icr2.check) #and indeed the icr-icr corrs have been removed

write.csv(flat.cor.mat.icr.ko.rm,"./corr_matrix_stats/ko_vs_icr/by_layer_resp/1000_Soils_drep_MAGs_ICR_subsoil_low_flat_stats_trimmed.csv",row.names = F)


#######adjust p, filter by correlation coefficient and write out#######

#### This is to make your and my life easier by reading the flattened correlation matrix (pre-generated), 
#### instead of building everything from scratch.
#### Comment/Un-comment the line below as you see fit.

#flat.cor.mat.icr.rm=read.csv("./corr_matrix_stats/ko_vs_icr/flat_stats_icr_icr_removed.csv",header = T) # only icr-icr removed
#flat.cor.mat.icr.rm=read.csv("./corr_matrix_stats/ko_vs_icr/flat_stats_icr_ko_removed.csv",header = T) # ko-ko and icr-icr removed
flat.cor.mat.icr.rm_1=read.csv("./corr_matrix_stats/ko_vs_icr/by_layer_resp/1000_Soils_drep_MAGs_ICR_subsoil_low_flat_stats_trimmed.csv",header = T)
flat.cor.mat.icr.rm_2=read.csv("./by_layer_respiration/ko_ko_removed/full_flat_stats/flat_stats_icr_ko_removed_TOP_Low.csv",header = T)
flat.cor.mat.icr.rm_3=read.csv("./by_layer_respiration/ko_ko_removed/full_flat_stats/flat_stats_icr_ko_removed_BTM_High.csv",header = T)
flat.cor.mat.icr.rm_4=read.csv("./by_layer_respiration/ko_ko_removed/full_flat_stats/flat_stats_icr_ko_removed_BTM_Low.csv",header = T)

p.fdr_1 = p.adjust(flat.cor.mat.icr.rm_1$p, method = "fdr")
flat.cor.mat.icr.rm.p.adj_1 = cbind(flat.cor.mat.icr.rm_1,p.fdr_1)

p.fdr_2 = p.adjust(flat.cor.mat.icr.rm_2$p, method = "fdr")
flat.cor.mat.icr.rm.p.adj_2 = cbind(flat.cor.mat.icr.rm_2,p.fdr_2)

p.fdr_3 = p.adjust(flat.cor.mat.icr.rm_3$p, method = "fdr")
flat.cor.mat.icr.rm.p.adj_3 = cbind(flat.cor.mat.icr.rm_3,p.fdr_3)

p.fdr_4 = p.adjust(flat.cor.mat.icr.rm_4$p, method = "fdr")
flat.cor.mat.icr.rm.p.adj_4 = cbind(flat.cor.mat.icr.rm_4,p.fdr_4)

#filter out rows rho < 0.40
flat.cor.mat.icr.rm.p.adj.r40 = flat.cor.mat.icr.rm.p.adj[which(abs(flat.cor.mat.icr.rm.p.adj$cor)>0.4),]
length(unique(flat.cor.mat.icr.rm.p.adj.r40$column))#XX highly significant ko icr associations
write.csv(flat.cor.mat.icr.rm.p.adj.r40,"./corr_matrix_stats/ko_vs_icr/ko_ko_removed/icr_ko_flat_r40.csv",row.names = F)

#filter out rows rho < 0.50
flat.cor.mat.icr.rm.p.adj.r50_1 = flat.cor.mat.icr.rm.p.adj_1[which(abs(flat.cor.mat.icr.rm.p.adj_1$cor)>0.5),]
length(unique(flat.cor.mat.icr.rm.p.adj.r50_1$column))#XX highly significant ko icr associations
write.csv(flat.cor.mat.icr.rm.p.adj.r50_1,"./corr_matrix_stats/ko_vs_icr/by_layer_respiration/ko_ko_removed/icr_ko_flat_r50_TOP_High.csv",row.names = F)

flat.cor.mat.icr.rm.p.adj.r50_2 = flat.cor.mat.icr.rm.p.adj_2[which(abs(flat.cor.mat.icr.rm.p.adj_2$cor)>0.5),]
length(unique(flat.cor.mat.icr.rm.p.adj.r50_2$column))#XX highly significant ko icr associations
write.csv(flat.cor.mat.icr.rm.p.adj.r50_2,"./corr_matrix_stats/ko_vs_icr/by_layer_respiration/ko_ko_removed/icr_ko_flat_r50_TOP_Low.csv",row.names = F)

flat.cor.mat.icr.rm.p.adj.r50_3 = flat.cor.mat.icr.rm.p.adj_3[which(abs(flat.cor.mat.icr.rm.p.adj_3$cor)>0.5),]
length(unique(flat.cor.mat.icr.rm.p.adj.r50_3$column))#XX highly significant ko icr associations
write.csv(flat.cor.mat.icr.rm.p.adj.r50_3,"./corr_matrix_stats/ko_vs_icr/by_layer_respiration/ko_ko_removed/icr_ko_flat_r50_BTM_Low.csv",row.names = F)

#filter out rows rho < 0.60
flat.cor.mat.icr.rm.p.adj.r60_1 = flat.cor.mat.icr.rm.p.adj_1[which(abs(flat.cor.mat.icr.rm.p.adj_1$cor)>0.6),]
#then filter out rows p.fdr 0.01
flat.cor.mat.icr.rm.p.adj.r60_fdr_0_01_1 = flat.cor.mat.icr.rm.p.adj.r60_1[which(flat.cor.mat.icr.rm.p.adj.r60_1$p.fdr<0.01),]
length(unique(flat.cor.mat.icr.rm.p.adj.r60_fdr_0_01_1$column))#XX highly significant ko icr associations
write.csv(flat.cor.mat.icr.rm.p.adj.r60_fdr_0_01_1,"./corr_matrix_stats/ko_vs_icr/by_layer_resp/1000_Soils_drep_MAGs_ICR_subsoil_low_r60_p_0_01.csv",row.names = F)

flat.cor.mat.icr.rm.p.adj.r60_2 = flat.cor.mat.icr.rm.p.adj_2[which(abs(flat.cor.mat.icr.rm.p.adj_2$cor)>0.6),]
#then filter out rows p.fdr 0.01
flat.cor.mat.icr.rm.p.adj.r60_fdr_0_01_2 = flat.cor.mat.icr.rm.p.adj.r60_2[which(flat.cor.mat.icr.rm.p.adj.r60_2$p.fdr<0.01),]
length(unique(flat.cor.mat.icr.rm.p.adj.r60_fdr_0_01_2$column))#XX highly significant ko icr associations
write.csv(flat.cor.mat.icr.rm.p.adj.r60_fdr_0_01_2,"./by_layer_respiration/ko_ko_removed/icr_ko_flat_r60_fdr_0_01_TOP_Low.csv",row.names = F)

flat.cor.mat.icr.rm.p.adj.r60_3 = flat.cor.mat.icr.rm.p.adj_3[which(abs(flat.cor.mat.icr.rm.p.adj_3$cor)>0.6),]
#then filter out rows p.fdr 0.01
flat.cor.mat.icr.rm.p.adj.r60_fdr_0_01_3 = flat.cor.mat.icr.rm.p.adj.r60_3[which(flat.cor.mat.icr.rm.p.adj.r60_3$p.fdr<0.01),]
length(unique(flat.cor.mat.icr.rm.p.adj.r60_fdr_0_01_3$column))#XX highly significant ko icr associations
write.csv(flat.cor.mat.icr.rm.p.adj.r60_fdr_0_01_3,"./by_layer_respiration/ko_ko_removed/icr_ko_flat_r60_fdr_0_01_BTM_High.csv",row.names = F)

flat.cor.mat.icr.rm.p.adj.r60_4 = flat.cor.mat.icr.rm.p.adj_4[which(abs(flat.cor.mat.icr.rm.p.adj_4$cor)>0.6),]
#then filter out rows p.fdr 0.01
flat.cor.mat.icr.rm.p.adj.r60_fdr_0_01_4 = flat.cor.mat.icr.rm.p.adj.r60_4[which(flat.cor.mat.icr.rm.p.adj.r60_4$p.fdr<0.01),]
length(unique(flat.cor.mat.icr.rm.p.adj.r60_fdr_0_01_4$column))#XX highly significant ko icr associations
write.csv(flat.cor.mat.icr.rm.p.adj.r60_fdr_0_01_4,"./by_layer_respiration/ko_ko_removed/icr_ko_flat_r60_fdr_0_01_BTM_Low.csv",row.names = F)

#filter out rows rho < 0.70
flat.cor.mat.icr.rm.p.adj.r70 = flat.cor.mat.icr.rm.p.adj[which(abs(flat.cor.mat.icr.rm.p.adj$cor)>0.7),]
length(unique(flat.cor.mat.icr.rm.p.adj.r70$column))#XX highly significant ko icr associations
write.csv(flat.cor.mat.icr.rm.p.adj.r70,"./corr_matrix_stats/ko_vs_icr/ko_ko_removed/icr_ko_flat_r70.csv",row.names = F)

#filter out rows rho < 0.75
flat.cor.mat.icr.rm.p.adj.r75 = flat.cor.mat.icr.rm.p.adj[which(abs(flat.cor.mat.icr.rm.p.adj$cor)>0.75),]
length(unique(flat.cor.mat.icr.rm.p.adj.r75$column))#XX highly significant ko icr associations
#write.csv(flat.cor.mat.icr.rm.p.adj.r75,"./corr_matrix_stats/ko_vs_icr/ko_ko_intact/icr_ko_flat_r75.csv",row.names = F)
write.csv(flat.cor.mat.icr.rm.p.adj.r75,"./corr_matrix_stats/ko_vs_icr/by_layer_respiration/ko_ko_removed/icr_ko_flat_r75_BTM_Low.csv",row.names = F)

#filter out rows rho < 0.80
flat.cor.mat.icr.rm.p.adj.r80_1 = flat.cor.mat.icr.rm.p.adj_1[which(abs(flat.cor.mat.icr.rm.p.adj_1$cor)>0.8),]
length(unique(flat.cor.mat.icr.rm.p.adj.r80_1$column))#XX highly significant ko icr associations
write.csv(flat.cor.mat.icr.rm.p.adj.r80_1,"./corr_matrix_stats/ko_vs_icr/by_layer_respiration/ko_ko_removed/icr_ko_flat_r80_TOP_High.csv",row.names = F)

flat.cor.mat.icr.rm.p.adj.r80_2 = flat.cor.mat.icr.rm.p.adj_2[which(abs(flat.cor.mat.icr.rm.p.adj_2$cor)>0.8),]
length(unique(flat.cor.mat.icr.rm.p.adj.r80_2$column))#XX highly significant ko icr associations
write.csv(flat.cor.mat.icr.rm.p.adj.r80_2,"./corr_matrix_stats/ko_vs_icr/by_layer_respiration/ko_ko_removed/icr_ko_flat_r80_TOP_Low.csv",row.names = F)

flat.cor.mat.icr.rm.p.adj.r80_3 = flat.cor.mat.icr.rm.p.adj_3[which(abs(flat.cor.mat.icr.rm.p.adj_3$cor)>0.8),]
length(unique(flat.cor.mat.icr.rm.p.adj.r80_3$column))#XX highly significant ko icr associations
write.csv(flat.cor.mat.icr.rm.p.adj.r80_3,"./corr_matrix_stats/ko_vs_icr/by_layer_respiration/ko_ko_removed/icr_ko_flat_r80_BTM_High.csv",row.names = F)

flat.cor.mat.icr.rm.p.adj.r80_4 = flat.cor.mat.icr.rm.p.adj_4[which(abs(flat.cor.mat.icr.rm.p.adj_4$cor)>0.8),]
length(unique(flat.cor.mat.icr.rm.p.adj.r80_4$column))#XX highly significant ko icr associations
write.csv(flat.cor.mat.icr.rm.p.adj.r80_4,"./corr_matrix_stats/ko_vs_icr/by_layer_respiration/ko_ko_removed/icr_ko_flat_r80_BTM_Low.csv",row.names = F)


#filter out rows rho < 0.90
flat.cor.mat.icr.rm.p.adj.r90 = flat.cor.mat.icr.rm.p.adj[which(abs(flat.cor.mat.icr.rm.p.adj$cor)>0.9),]
length(unique(flat.cor.mat.icr.rm.p.adj.r90$column))#XX highly significant ko icr associations
write.csv(flat.cor.mat.icr.rm.p.adj.r90,"./corr_matrix_stats/ko_vs_icr/ko_ko_intact/icr_icr_rm_flat_r90.csv",row.names = F)

#filter out rows rho < 0.925
flat.cor.mat.icr.rm.p.adj.r92.5 = flat.cor.mat.icr.rm.p.adj[which(abs(flat.cor.mat.icr.rm.p.adj$cor)>0.925),]
length(unique(flat.cor.mat.icr.rm.p.adj.r92.5$column))#XX highly significant ko icr associations
write.csv(flat.cor.mat.icr.rm.p.adj.r92.5,"./corr_matrix_stats/ko_vs_icr/icr_icr_rm_flat_r92_5.csv",row.names = F)

#filter out rows rho < 0.95
flat.cor.mat.icr.rm.p.adj.r95 = flat.cor.mat.icr.rm.p.adj[which(abs(flat.cor.mat.icr.rm.p.adj$cor)>0.95),]
length(unique(flat.cor.mat.icr.rm.p.adj.r95$column))#XX highly significant ko icr associations
write.csv(flat.cor.mat.icr.rm.p.adj.r95,"./corr_matrix_stats/ko_vs_icr/icr_icr_rm_flat_r95.csv",row.names = F)

#start with three zeroes

flat.cor.mat.icr.rm.p.adj.0.001 = flat.cor.mat.icr.rm.p.adj[which(flat.cor.mat.icr.rm.p.adj$p.fdr<0.001),]
length(unique(flat.cor.mat.icr.rm.p.adj.0.001$column))#XX viral cazys with highly significant mic phy associations
write.csv(flat.cor.mat.icr.rm.p.adj.0.001,"./corr_matrix_stats/ko_vs_icr/ko_ko_removed/icr_ko_flat_p_adj_0_001.csv",row.names = F)


flat.cor.mat.icr.rm.p.adj.0.0001 = flat.cor.mat.icr.rm.p.adj[which(flat.cor.mat.icr.rm.p.adj$p.fdr<0.0001),]
length(unique(flat.cor.mat.icr.rm.p.adj.0.0001$column))#XX viral cazys with highly significant mic phy associations
write.csv(flat.cor.mat.icr.rm.p.adj.0.0001,"./corr_matrix_stats/ko_vs_icr/ko_ko_removed/icr_ko_flat_p_adj_0_0001.csv",row.names = F)

#filter out rows fdr p > 0.000001
flat.cor.mat.icr.rm.p.adj.0.000001 = flat.cor.mat.icr.rm.p.adj[which(flat.cor.mat.icr.rm.p.adj$p.fdr<0.000001),]
length(unique(flat.cor.mat.icr.rm.p.adj.0.000001$column))#XX viral cazys with highly significant mic phy associations
#write.csv(flat.cor.mat.icr.rm.p.adj.0.000001,"./corr_matrix_stats/ko_vs_icr/ko_ko_intact/icr_ko_flat_p_adj_0_000001.csv",row.names = F)
write.csv(flat.cor.mat.icr.rm.p.adj.0.000001,"./corr_matrix_stats/ko_vs_icr/by_layer_respiration/ko_ko_removed/icr_ko_flat_p_adj_0_000001_BTM_Low.csv",row.names = F)

#filter out rows fdr p > 0.0000001
flat.cor.mat.icr.rm.p.adj.0.0000001 = flat.cor.mat.icr.rm.p.adj[which(flat.cor.mat.icr.rm.p.adj$p.fdr<0.0000001),]
length(unique(flat.cor.mat.icr.rm.p.adj.0.0000001$column))#XX viral cazys with highly significant mic phy associations
write.csv(flat.cor.mat.icr.rm.p.adj.0.0000001,"./corr_matrix_stats/ko_vs_icr/ko_ko_intact/icr_ko_flat_p_adj_0_0000001.csv",row.names = F)

#filter out rows fdr p > 0.00000001
flat.cor.mat.icr.rm.p.adj.0.00000001 = flat.cor.mat.icr.rm.p.adj[which(flat.cor.mat.icr.rm.p.adj$p.fdr<0.00000001),]
length(unique(flat.cor.mat.icr.rm.p.adj.0.00000001$column))#XX viral cazys with highly significant mic phy associations
write.csv(flat.cor.mat.icr.rm.p.adj.0.00000001,"./corr_matrix_stats/ko_vs_icr/icr_ko_flat_p_adj_0_0000001.csv",row.names = F)

#filter out rows fdr p > 0.000000001
flat.cor.mat.icr.rm.p.adj.0.000000001 = flat.cor.mat.icr.rm.p.adj[which(flat.cor.mat.icr.rm.p.adj$p.fdr<0.000000001),]
length(unique(flat.cor.mat.icr.rm.p.adj.0.000000001$column))#XX viral cazys with highly significant mic phy associations
write.csv(flat.cor.mat.icr.rm.p.adj.0.000000001,"./corr_matrix_stats/ko_vs_icr/icr_ko_flat_p_adj_0_00000001.csv",row.names = F)

#filter out rows fdr p > 0.0000000001
flat.cor.mat.icr.rm.p.adj.0.0000000001 = flat.cor.mat.icr.rm.p.adj[which(flat.cor.mat.icr.rm.p.adj$p.fdr<0.0000000001),]
length(unique(flat.cor.mat.icr.rm.p.adj.0.0000000001$column))#XX viral cazys with highly significant mic phy associations
write.csv(flat.cor.mat.icr.rm.p.adj.0.0000000001,"./corr_matrix_stats/ko_vs_icr/icr_ko_flat_p_adj_0_00000001.csv",row.names = F)


### Continuation from Line 158: The following section will conduct Independent Hypothesis Weighting (IHW) to 
### control the FDR and provide value of weights for each node to node relation.

#library("IHW")

#colnames(flat.cor.mat.icr.rm.p.adj.r60)

# Return object of the class ihwresult
#ihwRes <- ihw(p~cor, data=flat.cor.mat.icr.rm.p.adj.r60, alpha=0.1)
#ihwRes <- ihw(p~p.fdr, data=flat.cor.mat.icr.rm.p.adj.r60, alpha=0.1)
