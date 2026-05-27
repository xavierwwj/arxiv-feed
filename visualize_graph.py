"""
Visualise the LightRAG knowledge graph as an interactive HTML file.
Usage:
    pip install pyvis networkx
    python visualize_graph.py
Then open lightrag_graph.html in your browser.
"""

import os
import networkx as nx
from pyvis.network import Network

# Load LIGHTRAG_DIR from .env if present
LIGHTRAG_DIR = os.getenv("LIGHTRAG_DIR", "")
if not LIGHTRAG_DIR and os.path.exists(".env"):
    for line in open(".env"):
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, v = line.split("=", 1)
            if k == "LIGHTRAG_DIR":
                LIGHTRAG_DIR = v

if not LIGHTRAG_DIR or not os.path.exists(LIGHTRAG_DIR):
    raise FileNotFoundError(
        f"LIGHTRAG_DIR not found: '{LIGHTRAG_DIR}'. "
        "Set LIGHTRAG_DIR in your .env or as an environment variable."
    )

graphml_path = os.path.join(LIGHTRAG_DIR, "graph_chunk_entity_relation.graphml")
if not os.path.exists(graphml_path):
    raise FileNotFoundError(f"Graph file not found: {graphml_path}. Run ingest first.")

print(f"Loading graph from: {graphml_path}")
G = nx.read_graphml(graphml_path)
print(f"  {G.number_of_nodes()} nodes, {G.number_of_edges()} edges")

net = Network(
    height="95vh",
    width="100%",
    bgcolor="#0f0f1a",
    font_color="#e0e0e0",
    notebook=False,
    directed=True,
)
net.from_nx(G)

# Style nodes by degree (more connections = larger)
max_degree = max(dict(G.degree()).values(), default=1)
for node in net.nodes:
    degree = G.degree(node["id"])
    size = 10 + 30 * (degree / max_degree)
    node["size"] = size
    node["title"] = f"{node['id']}\nConnections: {degree}"
    node["color"] = {
        "background": "#4a9eff" if degree > max_degree * 0.3 else "#2a5a8f",
        "border": "#88ccff",
        "highlight": {"background": "#ff9f40", "border": "#ffcc80"},
    }

for edge in net.edges:
    edge["color"] = {"color": "#445566", "highlight": "#ff9f40"}
    label = edge.get("label") or edge.get("description", "")
    if label:
        edge["title"] = label[:120]  # tooltip on hover

net.set_options("""
{
  "physics": {
    "solver": "forceAtlas2Based",
    "forceAtlas2Based": {
      "gravitationalConstant": -60,
      "centralGravity": 0.005,
      "springLength": 120,
      "springConstant": 0.08
    },
    "stabilization": { "iterations": 150 }
  },
  "interaction": {
    "hover": true,
    "tooltipDelay": 100,
    "navigationButtons": true,
    "keyboard": true
  }
}
""")

output_path = os.path.join(LIGHTRAG_DIR, "lightrag_graph.html")
net.save_graph(output_path)
print(f"\nSaved to: {output_path}")
print("Open that file in your browser to explore the graph.")
