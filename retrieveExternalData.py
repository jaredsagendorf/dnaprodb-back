#!/usr/bin/env python
import os
import copy
import json
import subprocess
import glob
import argparse
import urllib
import urllib2
import re
import xmltodict
from dnaprodb_utils import C
#from Bio.PDB.MMCIF2Dict import MMCIF2Dict
from Bio import SwissProt
from Bio import SeqIO

arg_parser = argparse.ArgumentParser()
arg_parser.add_argument("-D", "--no_databases", action='store_true')
arg_parser.add_argument("-U", "--no_uniprot", action='store_true')
args = arg_parser.parse_args()

# Directories to store data files
ROOT_DIR = C["ROOT_DIR"]
UNIPROT_DIR = os.path.join(ROOT_DIR, "MAPPINGS/UNIPROT")
PDB_DIR = os.path.join(ROOT_DIR, "MAPPINGS/PDB")
CATH_DIR = os.path.join(ROOT_DIR, "MAPPINGS/CATH")
SIFTS_DIR = os.path.join(ROOT_DIR, "MAPPINGS/SIFTS")
GO_DIR = os.path.join(ROOT_DIR, "MAPPINGS/GO")
CIF_DIR = os.path.join(ROOT_DIR, "CIFFILES")
MAP_DIR = os.path.join(ROOT_DIR, "MAPPINGS")

# Database URLS
DATA = [
    # PDB sequence clusters
    ("ftp://resources.rcsb.org/sequence/clusters/bc-30.out", "bc-30.out", PDB_DIR), # 0
    ("ftp://resources.rcsb.org/sequence/clusters/bc-40.out", "bc-40.out", PDB_DIR), # 1
    ("ftp://resources.rcsb.org/sequence/clusters/bc-50.out", "bc-50.out", PDB_DIR), # 2
    ("ftp://resources.rcsb.org/sequence/clusters/bc-70.out", "bc-70.out", PDB_DIR), # 3
    ("ftp://resources.rcsb.org/sequence/clusters/bc-90.out", "bc-90.out", PDB_DIR), # 4
    ("ftp://resources.rcsb.org/sequence/clusters/bc-95.out", "bc-95.out", PDB_DIR), # 5
    ("ftp://resources.rcsb.org/sequence/clusters/bc-100.out", "bc-100.out", PDB_DIR), #6
    # CATH data
    ("ftp://orengoftp.biochem.ucl.ac.uk/cath/releases/daily-release/newest/cath-b-newest-all.gz", "cath_domains_list.dat.gz", CATH_DIR), #7
    # SIFTS mappings
    ("ftp://ftp.ebi.ac.uk/pub/databases/msd/sifts/flatfiles/csv/pdb_chain_uniprot.csv.gz", "uniprot_mappings.dat.gz", SIFTS_DIR), #8
    ("ftp://ftp.ebi.ac.uk/pub/databases/msd/sifts/flatfiles/csv/pdb_chain_go.csv.gz", "go_mappings.dat.gz", SIFTS_DIR), #9
    # GO ontology
    ("http://purl.obolibrary.org/obo/go.obo", "go.obo", GO_DIR) # 10
]

CLUSTERS = ["30", "40", "50", "70", "90", "95", "100"]

# Get list of valid PDBids
print("Getting list of PDB ids")
PDBIDS = {pdbid.strip().lower():{} for pdbid in open(os.path.join(CIF_DIR, "pdb_ids.dat"))}

# Download Data files
if(not args.no_databases):
    print("Downloading Data")
    for i in xrange(len(DATA)):
        url, fileName, dirName = DATA[i]
        print("Retrieving {}".format(url))
        try:
            REP = urllib2.urlopen(url)
            data = REP.read()
            REP.close()
            
            path = os.path.join(dirName, fileName)
            OUT = open(path, "w")
            OUT.write(data)
            OUT.close()
            
            # unzip data if needed
            prefix, suffix = os.path.splitext(fileName)
            if(suffix == ".gz"):
                subprocess.call(["gunzip", "-f", path])
                fileName = prefix
                DATA[i] = (url, fileName, dirName)
        except (urllib2.HTTPError, urllib2.URLError):
            print("Could not download {}".format(url))
else:
    for i in xrange(len(DATA)):
        url, fileName, dirName = DATA[i]
        prefix, suffix = os.path.splitext(fileName)
        if(suffix == ".gz"):
            fileName = prefix
            DATA[i] = (url, fileName, dirName)

# Download UniProt Data
if(not args.no_uniprot):
    print("Downloading UniProt files")
    url = 'https://www.uniprot.org/uploadlists/'
    params = {
        'from':'PDB_ID',
        'to':'ACC',
        'format':'txt',
        'query': ' '.join(PDBIDS.keys())
    }
    
    data = urllib.urlencode(params)
    request = urllib2.Request(url, data)
    response = urllib2.urlopen(request)
    path = os.path.join(UNIPROT_DIR, "uniprot_data.dat")
    FH = open(path, 'w')
    FH.write(response.read())
    FH.close()
    
    # split UniProt files
    print("Splitting UniProt data files")
    subprocess.call(["splitUNIPROT.pl", path, UNIPROT_DIR])

# Download PDB sequence files
print("Downloading PDB sequences")
url = "https://www.rcsb.org/pdb/download/downloadFastaFiles.do"
params = {
    'compressionType': 'uncompressed',
    'structureIdList': ' '.join(PDBIDS.keys())
}
data = urllib.urlencode(params)
request = urllib2.Request(url, data)
response = urllib2.urlopen(request)
path = os.path.join(PDB_DIR, "sequences.dat")
FH = open(path, 'w')
FH.write(response.read())
FH.close()

# Generate PDB sequence clusters
print("Generating Sequence Clusters")
CLUSTER_MAP = {} # maps PDBID_CHAIN to a sequence cluster identifier
for cluster in CLUSTERS:
    path = os.path.join(PDB_DIR, "bc-{}.out".format(cluster))
    FH = open(path)
    index = 1
    CLUSTER_MAP[cluster] = {}
    for line in FH:
        cid = "{}.{}".format(cluster, index)
        line = line.strip().split()
        for item in line:
            CLUSTER_MAP[cluster][item.strip()] = cid
        index += 1
    FH.close()

# Template for storing data about each PDBID
template = {
    "cath": {
        "H": [],
        "T": [],
        "A": [],
        "C": [],
        "seen": set()
    },
    "uniprot": {
        "accession": [],
        "names": ['N/A'],
        "organism": 'N/A',
        "seen": set()
    },
    "go": {
        "molecular_function": [],
        "biological_process": [],
        "cellular_component": [],
        "seen": set()
    },
    "clusters": {
        "30": 'N/A',
        "40": 'N/A',
        "50": 'N/A',
        "70": 'N/A',
        "90": 'N/A',
        "95": 'N/A',
        "100": 'N/A'
    },
    "chain_id": None
}

# Process data
# iterate over CATH data file
print("Reading in CATH data")
FH = open(os.path.join(DATA[7][2], DATA[7][1]))
for line in FH:
    line = line.split()
    pdbid = line[0][0:4].lower()
    chain = line[0][4]
    cath = line[2].split('.')
    
    if(pdbid not in PDBIDS):
        continue
    if(chain not in PDBIDS[pdbid]):
        PDBIDS[pdbid][chain] = copy.deepcopy(template)
        PDBIDS[pdbid][chain]["chain_id"] = chain
    
    Homology = '.'.join(cath[0:4])
    Topology = '.'.join(cath[0:3])
    Architecture = '.'.join(cath[0:2])
    Class = '.'.join(cath[0:1])
    if(Homology not in PDBIDS[pdbid][chain]["cath"]["seen"]):
        PDBIDS[pdbid][chain]["cath"]['H'].append(Homology)
        PDBIDS[pdbid][chain]["cath"]["seen"].add(Homology)
    if(Topology not in PDBIDS[pdbid][chain]["cath"]["seen"]):
        PDBIDS[pdbid][chain]["cath"]['T'].append(Topology)
        PDBIDS[pdbid][chain]["cath"]["seen"].add(Topology)
    if(Architecture not in PDBIDS[pdbid][chain]["cath"]["seen"]):
        PDBIDS[pdbid][chain]["cath"]['A'].append(Architecture)
        PDBIDS[pdbid][chain]["cath"]["seen"].add(Architecture)
    if(Class not in PDBIDS[pdbid][chain]["cath"]["seen"]):
        PDBIDS[pdbid][chain]["cath"]['C'].append(Class)
        PDBIDS[pdbid][chain]["cath"]["seen"].add(Class)
FH.close()

# iterate over UniProt mappings
print("Reading in UniProt mappings")
FH = open(os.path.join(DATA[8][2], DATA[8][1]))
UNP_RECORDS = {}
for line in FH:
    line = line.split(',')
    if(len(line) != 9):
        continue
    pdbid = line[0].lower().strip()
    chain = line[1].strip()
    accession = line[2].strip()
    
    if(pdbid not in PDBIDS):
        continue
    if(chain not in PDBIDS[pdbid]):
        PDBIDS[pdbid][chain] = copy.deepcopy(template)
        PDBIDS[pdbid][chain]["chain_id"] = chain
    if(accession in PDBIDS[pdbid][chain]['uniprot']['seen']):
        continue
    
    # Read extra data from UniProt file
    if(accession not in UNP_RECORDS):
        path = os.path.join(UNIPROT_DIR, accession[-1], "{}.txt".format(accession))
        if(not os.access(path, os.R_OK)):
            # file not found - try to download it individually
            try:
                url = "http://www.uniprot.org/uniprot/{}.txt".format(accession)
                handle = urllib2.urlopen(url)
                data = handle.read()
                handle.close()
                
                UNPOUT = open(os.path.join(UNIPROT_DIR, accession[-1], "{}.txt".format(accession)), "w")
                UNPOUT.write(data)
                UNPOUT.close()
            except:
                print("Could not retrieve uniprot record {}".format(accession))
                continue
        handle = open(path)
        UNP_RECORDS[accession] = SwissProt.read(handle)
        # format protein names
        names = []
        description = UNP_RECORDS[accession].description
        description = re.sub(r'{.*?}', '', description)
        description = re.split(':|;',description)
        for i in xrange(len(description)):
            description[i] = description[i].strip()
            if(re.search('^Full|^Short',description[i])):
                names.append(description[i].split('=')[1])
        UNP_RECORDS[accession].description = names
        handle.close()
    PDBIDS[pdbid][chain]['uniprot']['seen'].add(accession)
    PDBIDS[pdbid][chain]['uniprot']['accession'] += UNP_RECORDS[accession].accessions
    PDBIDS[pdbid][chain]['uniprot']['names'] = UNP_RECORDS[accession].description
    PDBIDS[pdbid][chain]['uniprot']['organism'] = UNP_RECORDS[accession].organism
    for DR in UNP_RECORDS[accession].cross_references:
        if(DR[0] == 'GO' and DR[1] not in PDBIDS[pdbid][chain]['go']['seen']):
            if(DR[2][0] == "F"):
                PDBIDS[pdbid][chain]['go']["molecular_function"].append({
                    "GO_ID": DR[1][3:],
                    "description": DR[2][2:]
                })
                PDBIDS[pdbid][chain]['go']['seen'].add(DR[1])
            elif(DR[2][0] == "P"):
                PDBIDS[pdbid][chain]['go']["biological_process"].append({
                    "GO_ID": DR[1][3:],
                    "description": DR[2][2:]
                })
                PDBIDS[pdbid][chain]['go']['seen'].add(DR[1])
            elif(DR[2][0] == "C"):
                PDBIDS[pdbid][chain]['go']["cellular_component"].append({
                    "GO_ID": DR[1][3:],
                    "description": DR[2][2:]
                })
                PDBIDS[pdbid][chain]['go']['seen'].add(DR[1])
FH.close()

# build GO ID map - this is so we can assign a name and branch to the mapped GO ids
print("Building GO ID maps")
GO_IDS = {}
FH = open(os.path.join(DATA[10][2], DATA[10][1]))
for line in FH:
    if(line.strip() == "[Term]"):
        goid = next(FH)[3:].strip()[3:]
        name = next(FH)[5:].strip()
        branch = next(FH)[10:].strip()
        GO_IDS[goid] = (name, branch)
FH.close()

# iterate over GO mappings
print("Reading in GO ID mappings")
FH = open(os.path.join(DATA[9][2], DATA[9][1]))
for line in FH:
    line = line.split(',')
    if(len(line) != 6):
        continue
    pdbid = line[0].lower().strip()
    chain = line[1].strip()
    go = line[5].strip()[3:]
    
    if(pdbid not in PDBIDS):
        continue
    if(chain not in PDBIDS[pdbid]):
        PDBIDS[pdbid][chain] = copy.deepcopy(template)
        PDBIDS[pdbid][chain]["chain_id"] = chain
    if(go in PDBIDS[pdbid][chain]['go']['seen']):
        continue
    PDBIDS[pdbid][chain]['go'][GO_IDS[go][1]].append({"GO_ID":go, "description":GO_IDS[go][0]})
    PDBIDS[pdbid][chain]['go']['seen'].add(go)
FH.close()

# ensure all PDBID chains are included
print("Filling in any missing chains")
sequences = SeqIO.parse(os.path.join(PDB_DIR, 'sequences.dat'), 'fasta')
for record in sequences:
    pdbid, chain = record.id.split('|')[0].split(':')
    pdbid = pdbid.lower()
    if(pdbid not in PDBIDS):
        continue
    elif(chain in PDBIDS[pdbid]):
        continue
    else:
        # add the chain
        PDBIDS[pdbid][chain] = copy.deepcopy(template)
        PDBIDS[pdbid][chain]["chain_id"] = chain

# write PDBID data to file
print("Writing PDB id info to file")
for pdbid in PDBIDS:
    d = pdbid[-1]
    for chain in PDBIDS[pdbid]:
        ckey = "{}_{}".format(pdbid.upper(), chain)
        # add sequence clusters
        for cluster in CLUSTERS:
            if(ckey in CLUSTER_MAP[cluster]):
                PDBIDS[pdbid][chain]["clusters"][cluster] = CLUSTER_MAP[cluster][ckey]
            else:
                PDBIDS[pdbid][chain]["clusters"][cluster] = 'N/A'
        
        # check for empty CATH data
        if(len(PDBIDS[pdbid][chain]["cath"]["H"]) == 0):
            PDBIDS[pdbid][chain]["cath"]["H"].append('N/A')
            PDBIDS[pdbid][chain]["cath"]["T"].append('N/A')
            PDBIDS[pdbid][chain]["cath"]["A"].append('N/A')
            PDBIDS[pdbid][chain]["cath"]["C"].append('N/A')
        
        # check for empty GO data
        if(
            len(PDBIDS[pdbid][chain]["go"]["molecular_function"]) == 0 and
            len(PDBIDS[pdbid][chain]["go"]["biological_process"]) == 0 and
            len(PDBIDS[pdbid][chain]["go"]["cellular_component"]) == 0
        ):
            PDBIDS[pdbid][chain]["go"]["molecular_function"].append({"description": 'N/A', "GO_ID": 'N/A'})
            PDBIDS[pdbid][chain]["go"]["biological_process"].append({"description": 'N/A', "GO_ID": 'N/A'})
            PDBIDS[pdbid][chain]["go"]["cellular_component"].append({"description": 'N/A', "GO_ID": 'N/A'})
        
        # check for empty Uniprot Data
        if(len(PDBIDS[pdbid][chain]['uniprot']['accession']) == 0):
            PDBIDS[pdbid][chain]['uniprot']['accession'].append('N/A')
        
        # remove sets
        del PDBIDS[pdbid][chain]["go"]["seen"]
        del PDBIDS[pdbid][chain]["cath"]["seen"]
        del PDBIDS[pdbid][chain]["uniprot"]["seen"]
    FH = open(os.path.join(MAP_DIR, "{}/{}.json".format(d, pdbid)), "w")
    FH.write(json.dumps(PDBIDS[pdbid]))
    FH.close()

# Write cluster mappings to file
for cluster in CLUSTERS:
    path = os.path.join(PDB_DIR, "bc-{}.maps".format(cluster))
    FH = open(path, "w")
    for ckey in CLUSTER_MAP[cluster]:
        pdbid, chain = ckey.split('_')
        cluster_id = CLUSTER_MAP[cluster][ckey]
        item = {
            "pdbid": pdbid.lower(),
            "chain_id": chain,
            "cluster_id": cluster_id,
            "sequence_identitiy": cluster
        }
        FH.write("{}\n".format(json.dumps(item)))
    FH.close()
