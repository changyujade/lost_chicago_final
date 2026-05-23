
# Chicago Lost Places

## Access the Lost Chicago dashboard 
https://lostchicagofinal-hfoea2p5s3lkia9jrjncpk.streamlit.app

This package builds a dashboard centering on historic Chicago sites that have been demolished and replaced. 

This package includes:
- `app_streamlit.py` — Streamlit dashboard with built-in data.
- `LostChicago.csv` - Our custom dataset.
- `chicago_neighborhoods.geojson` — official City of Chicago neighborhood boundaries
- `requirements.txt` — Python dependencies

## Install and run the app

```bash
pip install -r requirements.txt
streamlit run app.py
```

## Required CSV columns
- `name`
- `type`
- `neighborhood`
- `year_demolished`
- `img_link`
- `year_built`
- `lat`
- `lon`
- `cause`
- `replacement`
- `replacement_categories`
- `current_img`
- `source`
- `description`
