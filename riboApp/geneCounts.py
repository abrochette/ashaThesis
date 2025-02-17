from django_plotly_dash import DjangoDash
from dash import dcc, html, Input, Output, State
import plotly.express as px
import pandas as pd
from django_plotly_dash.models import DashApp
from riboApp.models import SelectedGene, ParquetData


app = DjangoDash("GeneScatter")

# ✅ Define the Layout
app.layout = html.Div([
    html.H1("Gene Scatter Plot"),
    dcc.Graph(id="scatter-plot"),
])

# Load gene count data (Modify as needed)
df = pd.DataFrame(list(ParquetData.objects.all().values("gene_name", "read_count")))

# Create the scatter plot
fig = px.scatter(df, x="read_count", y="read_count", hover_name="gene_name")

app.layout = html.Div([
    html.H1("Interactive Gene Scatter Plot"),
    dcc.Graph(id="gene-scatter-plot", figure=fig, style={"width": "80%", "height": "80vh"}),
    html.Div([
        html.H3("Clicked Genes"),
        dcc.Textarea(id="clicked-genes", style={"width": "100%", "height": "100px"}, readOnly=True),
        html.Button("Save Selected Genes", id="save-button", n_clicks=0),
        html.Div(id="save-status", style={"color": "green", "marginTop": "10px"})
    ]),
    dcc.Store(id="selected-genes-store", data=[]),
])

@app.callback(
    Output("selected-genes-store", "data"),
    Output("clicked-genes", "value"),
    Input("gene-scatter-plot", "clickData"),
    State("selected-genes-store", "data")
)
def update_selected_genes(clickData, current_genes):
    if clickData is None:
        return current_genes, "\n".join(current_genes)

    new_gene = clickData["points"][0]["hovertext"]
    if new_gene not in current_genes:
        current_genes.append(new_gene)

    return current_genes, "\n".join(current_genes)

@app.callback(
    Output("save-status", "children"),
    Input("save-button", "n_clicks"),
    State("selected-genes-store", "data")
)
def save_genes_to_db(n_clicks, gene_list):
    if n_clicks < 1:
        return ""

    if not gene_list:
        return "No genes selected, nothing to save."

    for gene in gene_list:
        SelectedGene.objects.get_or_create(gene_name=gene)

    return f"Saved {len(gene_list)} genes to database."