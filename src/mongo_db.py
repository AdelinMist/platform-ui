import streamlit as st
import pymongo
from utils.logger import logger
        
# Initialize connection.
# Uses st.cache_resource to only run once.
@st.cache_resource
def get_database():
    client = pymongo.MongoClient(**st.secrets["mongo"])
    db = client['platform']
    init_projects_collection(db)
    init_requests_collection(db)
    
    return db

def init_projects_collection(db):
    """
    Init the projects collection. 
    """
    coll_list = db.list_collection_names()
    
    if 'projects' not in coll_list:
        # Creating a new collection
        try:
            db.create_collection('projects')
        except Exception as e:
            logger.error(e)
            
    # Add the schema validation!
    db['projects'].create_index("name", unique=True)
    # db.command("collMod", "projects", validator=models.project.get_validator())
    
def init_requests_collection(db):
    """
    Init the requests collection. 
    """
    coll_list = db.list_collection_names()
    
    if 'requests' not in coll_list:
        # Creating a new collection
        try:
            db.create_collection('requests')
        except Exception as e:
            logger.error(e)
            
    # Add the schema validation!
    # db.command("collMod", "requests", validator=models.request.get_validator())
    
def init_service_collection(coll_name):
    db = get_database()
    coll_list = db.list_collection_names()
    
    if coll_name not in coll_list:
        # Creating a new collection
        try:
            db.create_collection(coll_name)
        except Exception as e:
            logger.error(e)