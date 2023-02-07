import numpy as np
import pandas as pd
import requests
import time
from datetime import datetime

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
    for index, row in references_df.iterrows():
        nodes[row['paperId']] = [row['title'], datetime.strptime(row['publicationDate'], '%Y-%m-%d'), row['year'], row['journal'], row['authors'], row['url']]
    # Make edges list with corpus-listed references
    edges = pd.DataFrame({"referencing": [json['paperId']]*len(references_df),
                          "referenced": references_df['paperId']})
    # For each reference, get its references and their metadata, and add them to the dicts
    for index, row in references_df.iterrows():
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