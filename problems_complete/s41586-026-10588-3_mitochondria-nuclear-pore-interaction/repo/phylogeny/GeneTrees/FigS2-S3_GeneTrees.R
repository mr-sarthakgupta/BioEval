### GENE TREES ###
# Plot and color gene trees for RANBP2 proteins

# Environment
### These don't all get used here but oh well
library(tidyverse)
library(magrittr)
library(patchwork)
library(ggrepel)
library(ggpubr)
library(viridis)
library(grDevices)
library(treeio)
library(ggtree)
library(ape)
library(Biostrings)
library(seqinr)
library(phangorn)

conflicted::conflict_prefer("select", "dplyr")
conflicted::conflict_prefer("filter", "dplyr")

# Compare distances (phangorn)
ctd_tree <- read.tree("RAxML_CTD/RAxML_bestTree.CTD_BEST")
full_tree <- read.tree("RAxML_Vertebrates/RAxML_bestTree.RANBP2_PROTEIN")

treedist(ctd_tree, full_tree)

# Full gene tree
tree <- full_tree
tree$tip.label <- tree$tip.label %>% gsub("_", " ", .)
grp <- list(mammals = tree$tip.label[c(54:185)],
            birds = tree$tip.label[c(16:51)],
            reptiles = tree$tip.label[c(6:15,52:53)],
            agnatha = tree$tip.label[c(4:5)])
p <- ggtree(tree, layout = "circular")
p <- groupOTU(p, grp, 'Species')

p + aes(color=Species) +
  theme(legend.position="none") +
  geom_treescale() +
  scale_color_manual(values = c("black", plasma(6)[c(2,3,5,4)])) +
  geom_tiplab2(size = 1.2) + 
  geom_strip('Alligator sinensis', 'Gekko japonicus', color = plasma(6)[4],
             label="Reptilia", offset = -0.75, offset.text = 0, barsize = 0, fontsize = 3) + 
  geom_strip('Struthio camelus', 'Catharus ustulatus',  color = plasma(6)[3],
             label="Aves", offset = -1, offset.text = 0, barsize = 0, fontsize = 3) +
  geom_strip('Tachyglossus aculeatus', 'Macaca mulatta',  color = plasma(6)[5],
             label="Mammalia", offset = 0, offset.text = 0.1, barsize = 0, fontsize = 3) +
  geom_strip('Gekko japonicus', 'Myxine glutinosa', ### weird start to adjust clipping
             color = plasma(6)[2],
             label="Agnatha", offset = -0.5, offset.text = 0, barsize = 0, fontsize = 3) 
### scalebar was moved in adobe illustrator

# CTD tree
tree <- read.raxml("RAxML_bipartitionsBranchLabels.CTD_FINAL")

# remove species that were not real CTD sequences
new.tree <- drop.tip.phylo(tree@phylo, "Strongylocentrotus_purpuratus") %>%
  drop.tip.phylo(., "Branchiostoma_belcheri") %>%
  drop.tip.phylo(., "Branchiostoma_floridae")
ggtree(new.tree) + geom_tiplab(size = 2, angle = 90) + coord_flip() + geom_treescale()

### tree was rerooted in R just for visualization purposes and then colored manually in
### illustrator by clade for final publication to match the gene tree
