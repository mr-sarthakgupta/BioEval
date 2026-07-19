# Plot omega from HyPhy FEL JSON output
# Environment
library(jsonlite)
library(tidyverse)

# Replicate ggplot default colors
gg_color_hue <- function(n) {
  hues = seq(15, 375, length = n + 1)
  hcl(h = hues, l = 65, c = 100)[1:n]
}

# Data
fel <- fromJSON("RANBP2-Vertebrate-Codon-Cleaned.fasta.FEL.json")
results <- fel$MLE$content$`0`
colnames(results) <- fel$MLE$headers[,1]
head(results)

# Reformat for ggplot
results %<>% as.data.frame() %>%
  rownames_to_column(var = "position") %>%
  mutate(omega = beta/alpha,
         position = as.numeric(position))

# Positive selection above limit gets capped
y_max <- 3  
results$omega_capped <- pmin(results$omega, y_max)
results$is_outlier <- results$omega > y_max

# Colors for p-value threshold
results %<>% mutate(color = case_when(`p-value` <= 0.05 ~ "red",
                                     TRUE ~ "black"))

# RANBP2 domain mouse coords --> alignment coords
### D1 1165-1301 --> 1165-1301
### D2 1849-1985 --> 1889-2025
### D3 2146-2282 --> 2186-2322
### D4 2740-2875 --> 2810-2945
### CTD 2896-3052 --> 2966-3123

evolution <- ggplot() +
  annotate(geom = "rect",xmin = 1165, xmax = 1301, ymin = 0, ymax = 3.1, fill = gg_color_hue(5)[1], alpha = 0.5) + # BD1
  annotate(geom = "rect",xmin = 1889, xmax = 2025, ymin = 0, ymax = 3.1, fill = gg_color_hue(5)[2], alpha = 0.5) + # BD2
  annotate(geom = "rect",xmin = 2186, xmax = 2322, ymin = 0, ymax = 3.1, fill = gg_color_hue(5)[3], alpha = 0.5) + # BD3
  annotate(geom = "rect",xmin = 2810, xmax = 2945, ymin = 0, ymax = 3.1, fill = gg_color_hue(5)[4], alpha = 0.5) + # BD4
  annotate(geom = "rect",xmin = 2966, xmax = 3123, ymin = 0, ymax = 3.1, fill = gg_color_hue(5)[5], alpha = 0.5) + # CTD
  geom_point(data = results[results$is_outlier, ],
    aes(x = position, y = omega_capped, color = color), shape = 17, alpha = 1, size = 1) + 
  geom_point(data = results[results$is_outlier == FALSE, ],
             aes(x = position, y = omega_capped, color = color), size = 0.5, alpha = 0.5) +
  scale_x_continuous(expand = c(0,0)) +
  scale_y_continuous(expand = c(0,0), limits = c(0,3.1)) +
  scale_color_manual(values = c(red = "red", black = "black"),
                     limits = c("red", "black"),
                     labels = c("p <= 0.05", "p > 0.05")) +
  xlab("Alignment Position") + ylab("Omega") + ggtitle("dN/dS along RANBP2 in Vertebrates") +
  theme_bw() + geom_hline(yintercept = 1, color = "blue", linetype = "dashed") +
  theme(panel.grid = element_blank(),
        text = element_text(size = 8),
        legend.position = "bottom") +
  guides(color = guide_legend(title = "Color", override.aes = list(shape = 16, size = 1, alpha = 1)))

evolution

## domain_plot and shannon_entropy from scripts in ProteinDomains/
domain_plot / shannon_entropy / evolution + plot_layout(heights = c(1.1, 2.5, 1))
