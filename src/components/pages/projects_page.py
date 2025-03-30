import streamlit as st
import pandas as pd
import math
import re
from pydantic import BaseModel, ValidationError
from typing import List
from mongo_db import upsert_projects, get_projects, delete_projects
from utils.validation.project import Project
from utils.misc import highlight_is_valid

def validate_df(df, validation_cls):
    """
    Runs a pydantic validation on the dataframe passed.
    Recreates the error dataframe based on current validation errors.
    Sets the 'is_valid' column on the dataframe based on validation results.
    """
    st.session_state["df_project_error"] = st.session_state["df_project_error"].iloc[0:0].copy()
    ValidationClass = validation_cls
    # Wrap the data_schema into a helper class for validation
    class ValidationWrap(BaseModel):
        df_dict: List[ValidationClass]
        
    df = df.assign(is_valid=True)
    validated_dict = {}
    
    try:
        df_dict = df.loc[:, df.columns != 'is_valid'].to_dict(orient="records")
        validated_dict = ValidationWrap(df_dict=df_dict).model_dump()['df_dict']
    except ValidationError as err:
        for err_inst in err.errors():
            invalid_index = err_inst['loc'][1]
            invalid_col = err_inst['loc'][2]
            st.session_state["df_project_error"].loc[invalid_index, invalid_col] = err_inst['msg']
            df.loc[invalid_index, 'is_valid'] = False
        
    return df, validated_dict

def submit_button_on_click(**kwargs):
    """
    Handles submission of new project!
    """
    projects = kwargs["projects"]
    
    projects_to_delete = st.session_state['deleted_projects']
    
    try:
        upsert_projects(projects)
        delete_projects(projects_to_delete)
        
        # trigger reset of the values from the db
        del st.session_state['df_project']
        del st.session_state['deleted_projects']
        st.snow()
    except Exception as err:
        st.exception(err)
    
    
class ProjectsPage():
    """
    This class exists to support the multipage architecture. This is a page to handle projects.
    """ 
    def __init__(self):
        self.cls = {}
        self.cls['name'] = Project.__name__
        self.cls['obj'] = Project
        
    def data_editor_on_change(self, **kwargs):
        """
        Runs on change of the data editor component.
        Handles the changed data, and updates the relevant dataframe.
        Runs the validation function on the newly changed dataframe.
        """
        cls_obj = self.cls['obj']
        state = st.session_state["df_project_edited"]
        
        for index, updates in state["edited_rows"].items():
            for key, value in updates.items():
                st.session_state["df_project"].loc[st.session_state["df_project"].index == index, key] = value
                
        for row in state["added_rows"]:
            df_row = pd.DataFrame.from_records([row])
            df_row = df_row.assign(id='')
            st.session_state["df_project"] = pd.concat([st.session_state["df_project"], df_row], ignore_index=True)
            
        for row_index in state["deleted_rows"][::-1]:
            if st.session_state["df_project"].loc[row_index, 'is_valid']:
                deleted_id = st.session_state["df_project"].iloc[row_index]['id']
                st.session_state['deleted_projects'].append(deleted_id)
            st.session_state["df_project"].drop(row_index, inplace=True)
            
        st.session_state["df_project"], st.session_state["dict_project"] = validate_df(st.session_state["df_project"], cls_obj)
        
    def upload_file(self):
        """
        Handles file uploading into the app.
        """
        cls_name = self.cls['name']
        cls_obj = self.cls['obj']
        
        if  'file_uploader_key' not in st.session_state:
            st.session_state['file_uploader_key'] = 0
        
        uploaded_file = st.file_uploader("Choose a CSV/JSON file", key=st.session_state['file_uploader_key'])
        if uploaded_file is not None:
            # Can be used wherever a "file-like" object is accepted:
            file_type = uploaded_file.name.split('.')[1]
            
            is_csv = file_type == 'csv'
            is_json = file_type == 'json'
            if is_csv:
                try:
                    dataframe = pd.read_csv(uploaded_file, index_col=0)
                except Exception as err:
                    st.exception(err)
            elif is_json:
                try:
                    dataframe = pd.read_json(uploaded_file, orient='records')
                except Exception as err:
                    st.exception(err)
            else:
                st.error("File was neither CSV or JSON! Please select a CSV/JSON file!")
            
            if is_json or is_csv:
                dataframe = dataframe.astype(str)
                
                # add the is_valid column if not existent
                if 'is_valid' not in dataframe.columns:
                    dataframe.assign(is_valid=False)
                
                # try to add the uploaded df to the saved one, throw exception if columns don't match
                if dataframe.columns.to_list() == st.session_state["df_project"].columns.to_list():
                    try:
                        st.session_state["df_project"] = pd.concat([st.session_state["df_project"], dataframe], ignore_index=True )
                    except Exception as err:
                        st.exception(err)
                    
                    st.session_state["df_project"], st.session_state["dict_project"] = validate_df(st.session_state["df_project"], cls_obj)
                    # this is a hack to make this whole function run once for each file uploaded.
                    st.session_state['file_uploader_key'] = st.session_state['file_uploader_key'] + 1
                    
                    st.rerun()
                else:
                    st.error("File didn't have the correct columns! Please load a matching file next time!")
                    st.session_state['file_uploader_key'] = st.session_state['file_uploader_key'] + 1
        
    def submit_new_project(self):
        """
        Handles the submission of a new project to be added to the db.
        """
        cls_name = self.cls['name']
        
        # handle download and data validity message
        submit_disabled = False if st.session_state["df_project"]['is_valid'].all() else True
        
        if submit_disabled:
            st.error(f"The values are not valid!")
            st.subheader('Errors')
            st.dataframe(st.session_state["df_project_error"].drop(columns=['id']), use_container_width=True)
        else:
            st.success(f"The values are valid!")
            
        dict_obj = st.session_state["dict_project"]

        submit_btn_name = f"submit_btn_{cls_name}"
        st.button(
            label="Submit Request",
            key=submit_btn_name,
            icon=":material/skull:",
            disabled=submit_disabled,
            on_click=submit_button_on_click,
            kwargs={'projects': dict_obj}
        )
    
    def run_page(self):
        """
        The 'main' fucntion of each page. Runs everything.
        """
        cls_name = self.cls['name']
        cls_obj = self.cls['obj']
        members = list(cls_obj.model_fields.keys())
        
        split_name = re.sub( r"([A-Z])", r" \1", cls_name).split()
        page_title = ' '.join(split_name)
        st.title(page_title)
        
        # Set up column config with the selectbox for Enum attributes
        column_cfg={
            "is_valid": st.column_config.TextColumn("IsValid", width="large", default=False),
        }
        
        for member in members:
            column_cfg.update({member: st.column_config.TextColumn(
                f"{member.capitalize()}",
                help=cls_obj.model_fields[member].description,
                width="large",
                required=True
            )})
                
        if  "df_project_error" not in st.session_state:
            # Create an empty DataFrame with column names
            st.session_state["df_project_error"] = pd.DataFrame(columns=[*members])
            
        if  "dict_project" not in st.session_state:
            # Create an empty DataFrame with column names
            st.session_state["dict_project"] = {}
            
        if  'deleted_projects' not in st.session_state:
            # Create an empty DataFrame with column names
            st.session_state['deleted_projects'] = []
            
        if  'df_project' not in st.session_state:
            # Create an empty DataFrame with column names
            project_data = get_projects()
            st.session_state["df_project"] = pd.DataFrame(project_data, columns=[*members, 'is_valid'])
            st.session_state["df_project"], st.session_state["dict_project"] = validate_df(st.session_state["df_project"], cls_obj)
            
        st.session_state["df_project_styled"] = st.session_state["df_project"].style.map(highlight_is_valid, subset=pd.IndexSlice[:, ['is_valid']])

        columns_to_display = list(st.session_state["df_project"].columns)
        if 'id' in columns_to_display:
            columns_to_display.remove('id')
            
        st.subheader('Editor')
        st.data_editor(
            st.session_state["df_project_styled"],
            column_config=column_cfg,
            column_order=columns_to_display,
            key="df_project_edited",
            disabled=["is_valid"],
            num_rows="dynamic",
            hide_index=False,
            on_change=self.data_editor_on_change,
            kwargs={'cls_name': cls_name, 'cls_obj': cls_obj},
            use_container_width=False,
            width=10000,
        )
        
        self.upload_file()
        
        if not st.session_state["df_project"].empty:
            self.submit_new_project()
        
    def get_page(self):
        """
        Returns the page object as needed.
        """
        url_pathname = 'projects'
        page_title = 'Projects'
        page_icon = ':material/sunny_snowing:' 
        return st.Page(self.run_page, title=page_title, icon=page_icon, url_path=url_pathname)