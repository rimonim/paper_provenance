import streamlit as st
import streamlit.components.v1 as components
import pandas as pd
import networkx as nx
from pyvis.network import Network
import textwrap
import pickle
import numpy as np
import requests
import time
from datetime import datetime

# FUNCTIONS
def get_provenance(seed_paper):
    """
    Given seed paper (url), generate nodes (dict) and edge list (dataframe) for its parents and grandparents.
    """
    nodes = dict()
    # Get metadata and references of seed paper
    http = requests.get("https://api.semanticscholar.org/graph/v1/paper/URL:%s?fields=title,year,publicationDate,journal,authors,url,references.title,references.publicationDate,references.year,references.journal,references.authors,references.url,embedding" %seed_paper)
    if http.status_code == 429:
        print("Waiting 5 Minutes for access to the API...")
        time.sleep(300)
        http = requests.get("https://api.semanticscholar.org/graph/v1/paper/URL:%s?fields=title,year,publicationDate,journal,authors,url,references.title,references.publicationDate,references.year,references.journal,references.authors,references.url,embedding" %seed_paper)
    json = http.json()
    # Put seed paper metadata into nodes dict
    nodes[json['paperId']] = [json['title'], datetime.strptime(json['publicationDate'], '%Y-%m-%d'), json['year'], json['journal'], json['authors'], json['url'], json['embedding']['vector']]
    # Put corpus-listed references into nodes dict
    references_df = pd.DataFrame(json['references']).dropna()
    references_df = references_df.set_index('paperId').reset_index()
    for index, row in references_df.iterrows():
        nodes[row['paperId']] = [row['title'], datetime.strptime(row['publicationDate'], '%Y-%m-%d'), row['year'], row['journal'], row['authors'], row['url']]
    # Make edges list with corpus-listed references
    edges = pd.DataFrame({"referencing": [json['paperId']]*len(references_df),
                          "referenced": references_df['paperId']})
    progress_bar.progress(1/len(references_df.index))
    # For each reference, get its references and their metadata, and add them to the dicts
    for index, row in references_df.iterrows():
        if index <= len(references_df.index):
            progress_bar.progress(0.9*index/len(references_df.index))
        # Get metadata and references of referenced paper
        temp_http = requests.get("https://api.semanticscholar.org/graph/v1/paper/%s?fields=title,year,publicationDate,journal,authors,url,references.title,references.publicationDate,references.year,references.journal,references.authors,references.url" %row['paperId'])
        if temp_http.status_code == 429:
            print("Waiting 5 Minutes for access to the SemanticScholar API...")
            time.sleep(300)
            temp_http = requests.get("https://api.semanticscholar.org/graph/v1/paper/%s?fields=title,year,publicationDate,journal,authors,url,references.title,references.publicationDate,references.year,references.journal,references.authors,references.url" %row['paperId'])
        if temp_http.status_code == 404:
            continue
        temp_json = temp_http.json()
        ## no need to put referenced paper metadata into nodes dict
        # Put corpus-listed reference references into nodes dict
        temp_references_df = pd.DataFrame(temp_json['references']).dropna()
        if len(temp_references_df) == 0:
            continue
        for i, r in temp_references_df.iterrows():
            nodes[r['paperId']] = [r['title'], datetime.strptime(r['publicationDate'], '%Y-%m-%d'), r['year'], r['journal'], r['authors'], r['url']]
        # Make edges list with corpus-listed reference references, and append to main edge list
        temp_edges = pd.DataFrame({"referencing": [temp_json['paperId']]*len(temp_references_df),
                                   "referenced": temp_references_df['paperId']})
        edges = pd.concat([edges, temp_edges])
        json[row['paperId']] = temp_json
    edges = edges.set_index("referencing").reset_index()
    # column: total times referenced
    edges['total_refs'] = edges.groupby(['referenced'])['referencing'].transform('count')
    # column: referencing is seed paper
    edges['direct_ref'] = edges['referencing'] == edges.iloc[0,0]
    return nodes, edges

def get_heading(paperId, nodes, edges):
    """Function: Gets pretty paper citation (nodes and edges from get_provenance)"""
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

@st.cache(max_entries=20, show_spinner=False, suppress_st_warning=True)   #-- cache data
def graph_provenance(url, min_refs):
    """Function: Generate html file with interactive graph"""
    # Retrieve data
    nodes, edges = get_provenance(url)
    
    # Save updated available papers list
    paperId = edges.iloc[0,0]
    seed_paper = get_heading(paperId, nodes, edges)
    available_papers_dict[seed_paper] = url
    if not seed_paper in available_papers_list:
        available_papers_list.insert(-1, seed_paper)
    with open("data/available_papers_dict.pkl", 'wb') as d:
        pickle.dump(available_papers_dict, d)
    with open("data/available_papers_list.pkl", 'wb') as l:
        pickle.dump(available_papers_list, l)
    
    # Abridged edge list
    abridged_edges = edges.loc[(edges['total_refs'] >= min_refs) | (edges['direct_ref'])]

    # Create networkx graph object
    G = nx.from_pandas_edgelist(abridged_edges,
                                source = 'referencing',
                                target = 'referenced',
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
        heading = get_heading(i, nodes, abridged_edges)
        node_label[i] = url+heading+"</a><br>"+textwrap.fill(title, 35)+"<br>"+textwrap.fill(journal, 35)
        
    nx.set_node_attributes(G, node_label, 'title')
    nx.set_node_attributes(G, " ", 'label')

    # Define node level as publication date (timestamp in years)
    node_level = dict()
    for i in nodes:
        node_level[i] = nodes[i][1].timestamp()/31536000

    nx.set_node_attributes(G, node_level, 'level')

    # Vary node size by number of citations (except source node)
    node_citations = (abridged_edges.loc[:,'referenced'].value_counts()*5).to_dict()
    node_citations[paperId] = max(abridged_edges.loc[:,'referenced'].value_counts()*5)
    nx.set_node_attributes(G, node_citations, 'size')

    # Vary node color by seed/parent/grandparent
    node_color = dict()
    for i in nodes:
        if i == paperId:
            node_color[i] = "#A5243D"
        elif i in list(abridged_edges.loc[:,'referenced'][abridged_edges['direct_ref']]):
            node_color[i] = "#B48291"
        else:
            node_color[i] = "#AFAAB9"

    nx.set_node_attributes(G, node_color, 'color')

    # Initiate pyvis network
    net = Network(bgcolor = 'black', 
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
    
    # Save, read, and return graph as HTML file locally
    filename = paperId+"_provenance.html"
    try:
        net.save_graph("/Users/louisteitelbaum/Projects/paper_provenance/html_files/"+filename)
        html = open("/Users/louisteitelbaum/Projects/paper_provenance/html_files/"+filename, 'r', encoding='utf-8')
        return seed_paper, html
    except:
        net.save_graph("html_files/"+filename)
        html = open("html_files/"+filename, 'r', encoding='utf-8').read()
        return seed_paper, html


# DATA RETRIEVAL
# list of available papers, with corresponding filenames (to be updated with with cached searches)
try:
    with open("data/available_papers_dict.pkl", 'rb') as d:
        available_papers_dict = pickle.load(d)
    with open("data/available_papers_list.pkl", 'rb') as l:
        available_papers_list = pickle.load(l)
except:
    available_papers_dict = {'Parr & Friston, 2017':'https://www.semanticscholar.org/paper/Working-memory%2C-attention%2C-and-salience-in-active-Parr-Friston/44b62057755cbf95baf78bf1b5a931da66f05c09'}
    available_papers_list = ['Parr & Friston, 2017', 'New Search']

# PAGE
seed_paper = st.sidebar.selectbox("Select a seed paper to visualize:", available_papers_list)

# New search by url
if seed_paper == 'New Search':
    url = st.sidebar.text_input('Input Semantic Scholar or arXiv URL:')
    if len(url) != 0:
        with st.spinner('Retrieving data from the SemanticScholar Database...'):
            progress_bar = st.progress(0)
            seed_paper, html = graph_provenance(url, 4)
            progress_bar.progress(1.0)
        st.sidebar.success('Done!')
else:
    with st.spinner("Preparing your graph..."):
        progress_bar = st.progress(0)
        seed_paper, html = graph_provenance(available_papers_dict[seed_paper], 4)
        progress_bar.progress(1.0)

with st.spinner("Preparing your graph..."):
    # Set header title
    if seed_paper != 'New Search':
        progress_bar.empty()
        st.title('Provenance of '+seed_paper)
        st.markdown('The x axis is time. Pink nodes are direct references (parents) of the seed paper, while grey nodes are references of references (grandparents). With the exception of the seed paper, nodes are sized in proportion to their number of citations within the graph. Grandparent papers with three or fewer references have been dropped to avoid clutter. Try dragging the nodes around!')

        # Load HTML file in HTML component for display on Streamlit page
        components.html(html, height=600)
    else:
        st.warning('Waiting for user input.')

# Explanation
st.subheader('What does this tool do?')
st.write(
    """
    There are many tools for searching the scientific literature. There are even tools for finding closely related works and visualizing them as connected nodes on a graph. But to my knowledge, this is the only tool for visualizing the history of a field leading up to the publication of your choosing. The graph should give you a sense of what the oldest important papers were (on the far left), when the major developments in the field occured (large nodes represent influential papers within this subfield), and when the largest mass of references were published (the widest portion of the graph). 
    The graph is force-directed, meaning that each connection is modelled as a spring, pulling its ends closer together. If you look carefully, you may make out individual chains of research that cluster together.
    """
)

# Footer
st.markdown(
    """
    <br>
    <h6><a href="https://github.com/rimonim/paper_provenance" target="_blank">GitHub Repo for this App</a></h6>
    """, unsafe_allow_html=True
    )
