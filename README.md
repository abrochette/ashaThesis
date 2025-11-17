# Ribosome Profiling Analysis Dashboard

A Django-based web application for analyzing ribosome profiling (Ribo-seq) and mRNA-seq data. This tool provides comprehensive analysis including PCA analysis, metagene plots, read length distribution, gene counts, and integrated Ribo-seq + mRNA comparisons.

## Features

- **Quality Control**: PCA analysis and P-site metagene plots to assess data quality
- **Read Length Analysis**: Visualize read length distributions across samples
- **Gene Count Analysis**: Raw and log₂-transformed gene expression levels
- **Advanced Analysis**: Delta analysis for replicate comparisons and bin counts for ribosome occupancy
- **Combined Analysis**: Integrated Ribo-seq and mRNA-seq comparisons
- **Preprocessing & Caching**: Pre-compute analyses for instant plot generation
- **Interactive Plots**: Plotly-based interactive visualizations with customizable axes

## Prerequisites

- Python 3.8+
- pip (Python package manager)
- Virtual environment (recommended)

## Installation

### 1. Clone the Repository

```bash
git clone <repository-url>
cd AshaThesis
```

### 2. Create and Activate Virtual Environment

**On macOS/Linux:**
```bash
python3 -m venv ~/.virtualenvs/djangoEnv
source ~/.virtualenvs/djangoEnv/bin/activate
```

**On Windows:**
```bash
python -m venv venv
venv\Scripts\activate
```

### 3. Install Dependencies

```bash
pip install -r requirements.txt
```

If `requirements.txt` doesn't exist, install the main dependencies:

```bash
pip install Django==5.2
pip install django-plotly-dash
pip install channels
pip install channels-redis
pip install django-crispy-forms
pip install crispy-bootstrap5
pip install pandas
pip install numpy
pip install plotly
pip install scipy
pip install scikit-learn
```

### 4. Set Up the Database

```bash
python manage.py migrate
```

### 5. Create a Superuser (Optional)

```bash
python manage.py createsuperuser
```

## Running the Application

### Start the Django Development Server

```bash
source ~/.virtualenvs/djangoEnv/bin/activate
python manage.py runserver
```

The application will be available at `http://127.0.0.1:8000/`

### Access the Application

- **Home Page**: `http://127.0.0.1:8000/`
- **Analysis Dashboard**: `http://127.0.0.1:8000/upload/` (main analysis page)
- **Admin Panel**: `http://127.0.0.1:8000/admin/` (if superuser created)

## Project Structure

```
AshaThesis/
├── manage.py                 # Django management script
├── db.sqlite3               # SQLite database
├── README.md                # This file
├── ashaThesis/              # Main Django project settings
│   ├── settings.py          # Project settings
│   ├── urls.py              # URL routing
│   ├── wsgi.py              # WSGI configuration
│   └── asgi.py              # ASGI configuration
├── riboApp/                 # Main Django application
│   ├── views.py             # View logic for analysis
│   ├── urls.py              # App URL patterns
│   ├── forms.py             # Django forms
│   ├── models.py            # Database models
│   ├── analysis/            # Analysis modules
│   ├── scripts/             # Preprocessing scripts
│   ├── templates/           # HTML templates
│   │   └── riboApp/
│   │       ├── base.html
│   │       ├── uploadParquet.html  # Main analysis dashboard
│   │       └── ...
│   └── static/              # CSS, JavaScript, images
├── media/                   # User uploads and data files
│   ├── parquetFiles/        # Uploaded parquet files
│   ├── parquetPickles/      # Cached analysis data
│   ├── mrnaFiles/           # mRNA data files
│   └── ...
└── tmp/                     # Temporary files and cache
```

## Usage

### 1. Upload Data Files

Navigate to the **Analysis Dashboard** and upload your data:
- **Riboseq Files**: Upload parquet files containing ribosome profiling data
- **mRNA Files**: Upload parquet files containing mRNA-seq data

### 2. Preprocess Files (Optional but Recommended)

Click **"Preprocess All Files"** to pre-compute all analyses. This takes 5-10 minutes but makes all future plots instant (< 1 second).

### 3. Run Analyses

Follow the recommended analysis flow:

1. **Quality Control** - Start with PCA and metagene plots
2. **Read Length Distribution** - Check read length patterns
3. **Gene Count Analysis** - Examine gene expression levels
4. **Advanced Analysis** - Delta analysis and bin counts
5. **Combined Analysis** - Compare Ribo-seq and mRNA data

### 4. Interactive Plots

All plots are interactive:
- Hover over data points for details
- Click legend items to toggle series
- Use toolbar to zoom, pan, and download plots
- Adjust axis bounds after plots are generated

## Data Format

### Parquet Files

Input data should be in Apache Parquet format with the following structure:

**Riboseq Data:**
- Columns: gene names, read counts, P-site positions, etc.

**mRNA Data:**
- Columns: gene names, expression counts, etc.

## Configuration

### Media Files

The application uses several reference files in the `media/` directory:

- `GRCm38.primary_assembly.genome.fa` - Genome FASTA file
- `gencode.vM25.annotation.gtf` - Gene annotation file
- `gencode.vM25.transcripts.fa` - Transcript sequences
- `stopcodons.gene_stopcodons.per_gene_majority.tsv` - Stop codon mappings
- `uorf_psite_offset.csv` - uORF P-site offset data

## Troubleshooting

### Server Won't Start

```bash
# Make sure virtual environment is activated
source ~/.virtualenvs/djangoEnv/bin/activate

# Check if port 8000 is in use
lsof -i :8000

# Kill process if needed
kill -9 <PID>
```

### Database Errors

```bash
# Reset database
rm db.sqlite3
python manage.py migrate
```

### Missing Dependencies

```bash
# Reinstall all requirements
pip install --upgrade -r requirements.txt
```

### Cache Issues

Clear the cache if plots aren't updating:

```bash
# Delete cache files
rm -rf media/parquetPickles/*
rm -rf media/mrnaPickles/*
```

## Development

### Running Tests

```bash
python manage.py test
```

### Creating Migrations

```bash
python manage.py makemigrations
python manage.py migrate
```

## Technologies Used

- **Backend**: Django 5.2
- **Frontend**: HTML, CSS, Bootstrap 5, JavaScript
- **Visualization**: Plotly, Plotly Dash
- **Data Processing**: Pandas, NumPy, SciPy, scikit-learn
- **Database**: SQLite (development), PostgreSQL (recommended for production)
- **Real-time**: Django Channels, Redis

## License

This project is part of academic research. Please contact the author for licensing information.

## Contact

For questions or issues, please contact the project maintainer.

