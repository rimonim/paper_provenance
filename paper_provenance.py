import streamlit as st
import streamlit.components.v1 as components
import pandas as pd
import networkx as nx
from pyvis.network import Network
import textwrap
import pickle
import get_provenance

# list of available papers, with corresponding filenames

try:
    with open("data/available_papers_dict.pkl", 'rb') as d:
        available_papers_dict = pickle.load(d)
    with open("data/available_papers_list.pkl", 'rb') as l:
        available_papers_list = pickle.load(l)
except:
    available_papers_dict = {'Friston (2010)':'friston', 'Jones et al. (2021)':'jones'}
    available_papers_list = ['Friston (2010)', 'Jones et al. (2021)', 'New Search']

seed_paper = st.selectbox("Select another seed paper to visualize:", available_papers_list)

# Function for getting paper title (requires access to nodes and edges)
def get_heading(paperId):
    title = nodes[paperId][0]
    year = str(round(nodes[paperId][2]))
    if len(nodes[paperId][4]) == 0:
        authors = "Unknown Authors"
    elif len(nodes[paperId][4]) == 1:
        authors = nodes[paperId][4][0]['name'].split()[-1]
    elif len(nodes[paperId][4]) == 2:
        authors = nodes[paperId][4][0]['name'].split()[-1]+" & "+nodes[paperId][4][1]['name'].split()[-1]
    else:
        authors = nodes[paperId][4][0]['name'].split()[-1]+" et al."
    return authors+", "+year

# New search by url
if seed_paper == 'New Search':
    url = st.text_input('Input Semantic Scholar or arXiv URL:')
    with st.spinner('Retrieving data from the SemanticScholar Database...'):
        nodes, edges = get_provenance(url)
        paperId = edges.iloc[0,0]
        seed_paper = get_heading(paperId)
        shortname = nodes[paperId][4][0]['name'].split()[-1].lower()
        available_papers_dict[seed_paper] = shortname
        available_papers_list.insert(-1, shortname)
        # Save data
        with open("data/"+shortname+"_nodes.pkl", 'wb') as n:
            pickle.dump(nodes, n)
        with open("data/available_papers_dict.pkl", 'wb') as d:
            pickle.dump(available_papers_dict, d)
        with open("data/available_papers_list.pkl", 'wb') as l:
            pickle.dump(available_papers_list, l)
        edges.to_csv("data/"+shortname+"_edges_complete.csv")

# Set header title
st.title('Provenance of '+seed_paper)
st.markdown('The x axis is time. Pink nodes are direct references (parents) of the seed paper, while grey nodes are references of references (grandparents). With the exception of the seed paper, nodes are sized in proportion to their number of citations within the graph.')

# weight_by_similarity (boolean, by default False)
# Currently not allowed for new searches
if seed_paper in available_papers_list:
    weight_by_similarity = st.checkbox("Weight edges by semantic similarity between papers?")
else:
    weight_by_similarity = False
    
# Read edges and nodes datasets (and set min_value)
if weight_by_similarity:
    edges = pd.read_csv("data/"+available_papers_dict[seed_paper]+"_edges.csv")
    attr = "length"
else:
    edges = pd.read_csv("data/"+available_papers_dict[seed_paper]+"_edges_complete.csv")
    attr = None

with open("data/"+available_papers_dict[seed_paper]+"_nodes.pkl", 'rb') as handle:
    nodes = pickle.load(handle)

# Abridged edge list
abridged_edges = edges.loc[(edges['total_refs'] >= 5) | (edges['direct_ref'])]

# Create networkx graph object
G = nx.from_pandas_edgelist(abridged_edges,
                            source = 'referencing',
                            target = 'referenced',
                            edge_attr=attr,
                            create_using = nx.Graph())

# Label nodes by name
node_label = dict()
for i in nodes:
    title = nodes[i][0]
    year = str(round(nodes[i][2]))
    url = "<a target=\"_blank\" href=\""+nodes[i][5]+"\">"
    if 'name' in nodes[i][3]:
        journal = nodes[i][3]['name']
    else:
        journal = "Unknown Journal"
    heading = get_heading(i)
    node_label[i] = url+heading+"</a><br>"+textwrap.fill(title, 40)+"<br>"+textwrap.fill(journal, 40)
    
nx.set_node_attributes(G, node_label, 'title')
nx.set_node_attributes(G, " ", 'label')
    
# Define node level as publication date
node_level = dict()
for i in nodes:
    node_level[i] = nodes[i][1].timestamp()/31536000

nx.set_node_attributes(G, node_level, 'level')

# Vary node size by number of citations (except source node)
node_citations = (abridged_edges.loc[:,'referenced'].value_counts()*5).to_dict()
node_citations[abridged_edges.iloc[0,0]] = 50
nx.set_node_attributes(G, node_citations, 'size')

# Vary node color by seed/parent/grandparent
node_color = dict()
for i in nodes:
    if i == abridged_edges.iloc[0,0]:
        node_color[i] = "#A5243D"
    elif i in list(abridged_edges.loc[:,'referenced'][abridged_edges['direct_ref']]):
        node_color[i] = "#B48291"
    else:
        node_color[i] = "#AFAAB9"

nx.set_node_attributes(G, node_color, 'color')

# Initiate pyvis network

net = Network(bgcolor = '#222222', 
              font_color = 'white', 
              layout = True, 
              directed = False)

net.from_nx(G)

# Set appropriate options
net.set_options("""
const options = {
  "nodes": {
    "borderWidthSelected": 3,
    "opacity": 0.8,
    "font": {
      "size": 12
    },
    "size": null
  },
  "edges": {
    "color": {
      "opacity": 0.5
    },
    "hoverWidth": 5,
    "scaling": {
      "max": 25
    },
    "selectionWidth": 5,
    "selfReferenceSize": null,
    "selfReference": {
      "angle": 0.7853981633974483
    },
    "smooth": false,
    "width": 5
  },
  "layout": {
    "hierarchical": {
      "enabled": true,
      "levelSeparation": 50,
      "direction": "LR"
    }
  },
  "interaction": {
    "hover": true
  },
  "physics": {
    "hierarchicalRepulsion": {
      "centralGravity": 0,
      "springConstant": 0.1,
      "nodeDistance": 200,
      "avoidOverlap": null,
      "dampening": 0.5
    },
    "minVelocity": 0.75,
    "solver": "hierarchicalRepulsion"
  }
}
""")

filename = available_papers_dict[seed_paper]+"_provenance.html"

# Save and read graph as HTML file locally
net.save_graph("html_files/"+filename)
html = open("html_files/"+filename, 'r', encoding='utf-8')

# Load HTML file in HTML component for display on Streamlit page
components.html(html.read(), height=500)

# Footer
st.markdown(
    """
    <br>
    <h6><a href="https://github.com/rimonim/paper_provenance" target="_blank">GitHub Repo for this App</a></h6>
    """, unsafe_allow_html=True
    )
