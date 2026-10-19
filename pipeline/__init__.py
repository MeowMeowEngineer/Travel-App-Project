"""WebforAI regional bridge-site pipeline (Gunsan v1).

Modules
- textutil  : text cleaning, slugs, hashes
- schema    : entity/field definitions, licence codes, labels
- maplinks  : map / navigation links (precise vs search)
- tourapi   : TourAPI client with disk cache
- importer  : CSV -> places.json (contract for collectors / v0 data)
- enrich    : match entities to TourAPI and fill facts, geo, nearby, images
- jsonld    : schema.org graphs
- build     : static site renderer
- validate  : QA checks and report
"""

__version__ = "0.1.0"
