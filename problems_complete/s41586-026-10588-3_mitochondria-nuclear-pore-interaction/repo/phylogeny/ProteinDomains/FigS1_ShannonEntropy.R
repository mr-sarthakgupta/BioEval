### SHANNON ENTROPY ###
# Calculate Shannon entropy in protein alignments filtered by missingness, plot

# Environment
## probably not all necessary but I don't remember
library(tidyverse)
library(magrittr)
library(patchwork)
library(ggpubr)
library(grDevices)
library(ape)
library(Biostrings)
library(seqinr)
library(patchwork)

conflicted::conflict_prefer("select", "dplyr")
conflicted::conflict_prefer("filter", "dplyr")

# Functions
### recreate ggplot default color scheme
gg_color_hue <- function(n) {
  hues = seq(15, 375, length = n + 1)
  hcl(h = hues, l = 65, c = 100)[1:n]
}

### Remove columns with X prop gaps but keep the indices
filter_alignment_by_gaps <- function(aln_mat, max_gap_prop = 0.2) {
  aln_mat <- as.matrix(aln_mat)
  gap_props <- apply(aln_mat, 2, function(col) mean(col == "-"))
  keep_cols <- which(gap_props <= max_gap_prop)
  filtered_mat <- aln_mat[, keep_cols, drop = FALSE]
  return(list(filtered = filtered_mat,
              kept_positions = keep_cols))
}

# Shannon entropy calculation
                     
# Arthropod RANBP2 (Nup385) domains
### Domain Drosophila start-end --> alignment start-end
### D1 1309-1445 --> 2722-2882
### D2 1605-1742 --> 3665-3988
### D3 2019-2151 --> 5354-5535
### D4 2556-2699 --> 7386-7541

# Arthropod alignment and entropy calculation
art_alignment <- read.alignment(file = "RANBP2-Arthropods-Prot-AlignedReformatted.fasta",
                            format = "fasta", forceToLower = FALSE)
char_mat <- do.call(rbind, lapply(art_alignment$seq, function(s) unlist(strsplit(s, ""))))
filtered_mat <- filter_alignment_by_gaps(char_mat, max_gap_prop = 0.75)

entropy <- apply(filtered_mat$filtered, 2, function(col) {
  probs <- table(col) / length(col)
  -sum(probs * log2(probs + 1e-8))
})

# base plot
plot(entropy, type = "p", ylab = "Shannon Entropy", xlab = "Alignment Position",
     main = "Per-site Entropy")

# ggplot data
position <- filtered_mat$kept_positions
art_entropy_df <- data.frame(position, entropy)
                                  
# Vertebrate RANBP2 domains
### Domain mouse start-end --> alignment start-end
### D1 1165-1301 --> 1462-1598
### D2 1849-1985 --> 3628-3764
### D3 2146-2282 --> 3957-4101
### D4 2740-2875 --> 5185-5321
### CTD 2896-3052 --> 5356-5502
                                  
# Vertebrate alignment and entropy calculation
vert_alignment <- read.alignment(file = "RANBP2-Vertebrate-Prot-AlignedReformatted.fasta",
                            format = "fasta", forceToLower = FALSE)
char_mat <- do.call(rbind, lapply(vert_alignment$seq, function(s) unlist(strsplit(s, ""))))
filtered_mat <- filter_alignment_by_gaps(char_mat, max_gap_prop = 0.75)

entropy <- apply(filtered_mat$filtered, 2, function(col) {
  probs <- table(col) / length(col)
  -sum(probs * log2(probs + 1e-8))
})

# base plot
plot(entropy, type = "p", ylab = "Shannon Entropy", xlab = "Alignment Position",
     main = "Per-site Entropy")

# ggplot data
position <- filtered_mat$kept_positions
vert_entropy_df <- data.frame(position, entropy)

# PLOT
# Set axes and shared labels
ymin <- min(c(art_entropy_df$entropy, vert_entropy_df$entropy))
ymax <- art_entropy_df$entropy %>% max + 0.1
labs <- labs(x = "Alignment Position", y = "Shannon Entropy") 

shannon_entropy <- ggplot(art_entropy_df, aes(x = position, y = entropy)) +
  annotate(geom = "rect", xmin = 2722, xmax = 2882, ymin = ymin, ymax = ymax, fill = gg_color_hue(5)[1], alpha = 0.5) + # BD1
  annotate(geom = "rect",xmin = 3665, xmax = 3988, ymin = ymin, ymax = ymax, fill = gg_color_hue(5)[2], alpha = 0.5) + # BD2
  annotate(geom = "rect",xmin = 5354, xmax = 5535, ymin = ymin, ymax = ymax, fill = gg_color_hue(5)[3], alpha = 0.5) + # BD3
  annotate(geom = "rect",xmin = 7386, xmax = 7541, ymin = ymin, ymax = ymax, fill = gg_color_hue(5)[4], alpha = 0.5) + # BD4
  #geom_col(fill = "gray40", alpha = 0.4, width = 1) + ggtitle("Arthropod Nup358") + labs +
  geom_line(color = "red", alpha = 0.5, size = 0.25) + ggtitle("Arthropod Nup358") + labs +
  geom_smooth(method = "loess", span = 0.01, color = "black", se = FALSE, size = 1) +
  scale_x_continuous(expand = c(0,0)) + scale_y_continuous(expand = c(0,0), limits = c(ymin, ymax)) +
  theme_bw() + geom_hline(yintercept = 2, color = "blue", linetype = "dashed") +
  theme(panel.grid = element_blank(),
        text = element_text(size = 8)) +
ggplot(vert_entropy_df, aes(x = position, y = entropy)) +
  annotate(geom = "rect",xmin = 1462, xmax = 1598, ymin = ymin, ymax = ymax, fill = gg_color_hue(5)[1], alpha = 0.5) + # BD1
  annotate(geom = "rect",xmin = 3628, xmax = 3764, ymin = ymin, ymax = ymax, fill = gg_color_hue(5)[2], alpha = 0.5) + # BD2
  annotate(geom = "rect",xmin = 3957, xmax = 4101, ymin = ymin, ymax = ymax, fill = gg_color_hue(5)[3], alpha = 0.5) + # BD3
  annotate(geom = "rect",xmin = 5185, xmax = 5321, ymin = ymin, ymax = ymax, fill = gg_color_hue(5)[4], alpha = 0.5) + # BD4
  annotate(geom = "rect",xmin = 5356, xmax = 5502, ymin = ymin, ymax = ymax, fill = gg_color_hue(5)[5], alpha = 0.5) + # CTD
  geom_line(color = "red", alpha = 0.5, size = 0.25) + ggtitle("Vertebrate RANBP2") + labs +
  geom_smooth(method = "loess", span = 0.01, color = "black", se = FALSE, size = 1) +
  scale_x_continuous(expand = c(0,0)) + scale_y_continuous(expand = c(0,0), limits = c(ymin, ymax)) +
  theme_bw() + geom_hline(yintercept = 2, color = "blue", linetype = "dashed") +
  theme(panel.grid = element_blank(),
        text = element_text(size = 8)) + plot_layout(nrow = 2, axis_titles = "collect")

shannon_entropy

### domain_plot data is from the other FigS1 code
domain_plot <- ggplot() +
  geom_segment(lengths, mapping = aes(x = start, xend = end, y = 0, yend = 0)) +
  geom_rect(domains, mapping = aes(xmin = start, xmax = end, ymin = -1, ymax = 1, fill = description, group = species), color = "black") +
  scale_x_continuous(limits = c(0, hum_length), expand = c(0,0)) +
  theme_minimal() +
  theme(axis.title.y = element_blank(),
        axis.text.y = element_blank(),
        axis.ticks.y = element_blank(),
        legend.position = "bottom",
        text = element_text(size = 8)) +
  labs(x = "Amino Acid Position", title = paste("Domains in RANBP2 homologs")) +
  guides(fill = guide_legend(title = "Domain")) +
  facet_grid(species~., switch = "y")

# Actual plot for publication, a and b tags added manually in adobe illustrator
domain_plot / shannon_entropy + plot_layout(heights = c(1, 2.5))
