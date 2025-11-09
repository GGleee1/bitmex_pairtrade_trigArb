Script for automated pair trading on Bitmex.

Builds on existing bitmex_pairtrade project to handle some of its former limitations: 

1. Can handle >2 securities, and potentially more with some additional changes.
2. Converts order sizes from USD terms to same units (usually num contracts) when sending orders, and vice versa when receiving orderbook data.
