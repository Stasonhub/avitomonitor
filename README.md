avitomonitor
============

Simple Avito.ru monitor

Works:
- AvitoParser class fetchs search results page, parses it and gets properties for items: title, price, city, date, company, url and photo url
- Parser class can save results into db and load them from it
- Parser crawls through pages
  - pages number limited by maxpages constant (by default = 5)
  - smart refresh: if no new items found on current page, next pages are not requested (assuming results ordered by addition time)
- Parser checks if there was no results for query or if search query was corrected (what brings lots of irrelevant results) and reports about it
- monitor.py:
  - one can specify the location, multiple search queries, multiple categories
  - new results are printed, sent to the message bus (needs notify-send installed) and saved
  - refreshes results every 60 seconds (adjustable)

Doesn't work
- does not distinguish ad items