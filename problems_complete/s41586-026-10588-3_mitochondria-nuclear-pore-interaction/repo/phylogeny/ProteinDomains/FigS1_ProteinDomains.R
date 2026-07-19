library(httr)
library(jsonlite)
library(tidyverse)

### Get data from Uniprot
hum_id <- "P49792" # human, 3224AA
mus_id <- "Q9ERU9" # mouse, 3053AA
dro_id <- "A0A0B4K7J2" # fruitfly, 2718AA


hum_url <- paste0("https://rest.uniprot.org/uniprotkb/", hum_id, ".json")
mus_url <- paste0("https://rest.uniprot.org/uniprotkb/", mus_id, ".json")
dro_url <- paste0("https://rest.uniprot.org/uniprotkb/", dro_id, ".json")

response <- GET(hum_url)
hum_data <- content(response, "parsed")

response <- GET(mus_url)
mus_data <- content(response, "parsed")

response <- GET(dro_url)
dro_data <- content(response, "parsed")

# Extract domain annotations
hum_features <- hum_data$features
hum_domains <- Filter(function(x) x$type == "Domain", hum_features)

mus_features <- mus_data$features
mus_domains <- Filter(function(x) x$type == "Domain", mus_features)

dro_features <- dro_data$features
dro_domains <- Filter(function(x) x$type == "Domain", dro_features)

# Create a data.frame for plotting
hum_domain_df <- do.call(rbind, lapply(hum_domains, function(x) {
  data.frame(start = x$location$start$value,
             end = x$location$end$value,
             description = x$description)
}))

mus_domain_df <- do.call(rbind, lapply(mus_domains, function(x) {
  data.frame(start = x$location$start$value,
             end = x$location$end$value,
             description = x$description)
}))

dro_domain_df <- do.call(rbind, lapply(dro_domains, function(x) {
  data.frame(start = x$location$start$value,
             end = x$location$end$value,
             description = x$description)
}))

# Plotting
hum_length <- 3224
mus_length <- 3053
dro_length <- 2718

lengths <- data.frame(start = c(0, 0, 0),
                      end = c(3224, 3053, 2718),
                      species = c("human", "mouse", "drosophila")) %>%
  mutate(species = factor(species, levels = c("human", "mouse", "drosophila")))

domains <- rbind(mutate(hum_domain_df, species = "human"),
                 mutate(mus_domain_df, species = "mouse")) %>%
  rbind(mutate(dro_domain_df, species = "drosophila")) %>%
  mutate(species = factor(species, levels = c("human", "mouse", "drosophila")),
         description = factor(description, levels = c("RanBD1 1", "RanBD1 2", "RanBD1 3", "RanBD1 4", "PPIase cyclophilin-type")))

domain_plot <- ggplot() +
  geom_segment(lengths, mapping = aes(x = start, xend = end, y = 0, yend = 0)) +
  geom_rect(domains, mapping = aes(xmin = start, xmax = end, ymin = -1, ymax = 1, fill = description, group = species), color = "black") +
  scale_x_continuous(limits = c(0, hum_length), expand = c(0,0)) +
  theme_minimal() +
  theme(axis.title.y = element_blank(),
        axis.text.y = element_blank(),
        axis.ticks.y = element_blank()) +
  labs(x = "amino acid position", title = paste("Domains for RanBP2 homologs")) +
  guides(fill = guide_legend(title = "domain")) +
  facet_grid(species~., switch = "y")
