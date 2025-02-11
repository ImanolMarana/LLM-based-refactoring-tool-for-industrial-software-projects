import requests
import json
import time
import llm
import sqlite3
import os
import pathlib
import textwrap
import google.generativeai as genai
import anthropic
import time
from dotenv import load_dotenv
from IPython.display import display
from IPython.display import Markdown

from fileManagement import getFileLocation, loadProperties, loadJavaFile, loadOtherFile, writeFile
from methodRefactoring import refactorMethod



def getSonarKey(local, properties):
  if(local):
    key = properties.get("sonarKey").data
  else:
    key = os.environ.get("SONAR_API_TOKEN")
  
  return key



def getLLMKey(local, properties):
  if(local == "True"):
    key =  properties.get("llmKey").data
  else:
    key =  os.environ.get("LLM_KEY")
  
  return key



def setLLM(local, properties, modelName):
  llmKey = getLLMKey(local, properties)
  
  match modelName:
    case "gemini":
      GOOGLE_API_KEY = llmKey 
      genai.configure(api_key=GOOGLE_API_KEY)
      model = genai.GenerativeModel('gemini-1.5-pro-latest')
    case "GPT-4":
      model = llm.get_model("gpt-4")
      model.key = llmKey
    case "GPT-4-turbo":
      model = llm.get_model("gpt-4-turbo")
      model.key = llmKey
    case "claude":
      model_aux = anthropic.Anthropic(
        api_key=llmKey,
      )
      model = [model_aux, "claude-3-5-sonnet-20241022"]
    case default:
      print(modelName)
      
  return model
  
  
  
def getIssueType(issue_message):  
  if("Cognitive Complexity" in issue_message):
    ret = "method"
  else:
    ret = "other"
    
  return ret
  


def printTotalResults(failed1, failed2, failed3, failed4, success):
  print(f"---------------------------------------------------------------------------------")
  print(f"LLMs lines errors: {failed1}")
  print(f"Formating errors: {failed2}")
  print(f"Applying errors: {failed3}")
  print(f"DB errors: {failed4}")
  print(f"---------------------------------------------------------------------------------")
  print(f"Successes: {success}")
  
  
  
def processIssues(issue, sonar_project, properties, model, model_type, sleep_time):
  # Get the issue key, line number and refactoring message
  issue_message = issue["message"]
  
  issue_type = getIssueType(issue_message)

  # match issue_type:
  #   case "cog":
  if("Cognitive Complexity" in issue_message):
    issue_line = issue["line"]
    #issue_line = issue["textRange"]["startLine"]
    issue_location = issue['component'].split(':')[1]
    issue_file_location = f"{sonar_project}/{issue_location}"
    
    input_path = properties.get("inputPath").data
    output_path = properties.get("outputPath").data
    db_path = properties.get("dbPath").data
    
    file_location = getFileLocation(properties, issue_file_location)
    original_file_location = f"{input_path}/{file_location}"
    refactoring_file_location = f"{output_path}/{file_location}"
    database_location = f"{db_path}/{file_location}"
    
    # Extract the code from the file that is going to be refactored and number the lines for the future prompts
    [code, skipped_lines, skipped_code] = loadJavaFile(original_file_location)
    #[code, skipped_lines, skipped_code] = loadOtherFile(original_file_location)
    
    # Get the code snippet
    if((code != '-1') and (len(code) < 60000)):
      #print(f"Detected issue: {issue}.")    
      print(f"Issue message: {issue_message}")  
      print(f"Issue line: {issue_line}")
      print(f"Skipped lines: {skipped_lines}")
      
      [code, refactored_file] = refactorMethod(code, issue, skipped_lines, skipped_code, sonar_project, model, model_type, sleep_time)
      if(code == 0):
        writeFile(refactoring_file_location, refactored_file)
        
    else:
      code = 1
      
  else:
    code = 2
  
  # Result code meaning:
  # Code -4 means database error \
  # Code -3 means refactoring application error \
  # Code -2 means response formating error \
  # Code -1 means LLM error \
  # Code 0 means success \
  # Code 1 means that the refactoring was the aimed issue but not processed \
  # Code 2 means that the file was not processed  
  return code


def main():
  load_dotenv("properties.env")
  
  properties = loadProperties()
  
  # Set your SonarCloud API token and project key
  local_sonar_api_key = properties.get("sonarLocalKey").data
  api_token = getSonarKey(local_sonar_api_key, properties)
  
  projects_to_analyse = properties.get("projectKeysToUse").data
  project_keys = properties.get(projects_to_analyse).data.split(', ')
  
  # Set the LLM model and API key
  local_llm_key = properties.get("llmLocalKey").data
  model_type = properties.get("llm").data
  model = setLLM(local_llm_key, properties, model_type)
  
  sleep_time = properties.get("sleepTime").data
  
  start = time.time()
  
  print(model)
  
  for project_key in project_keys:
  
    print("{}{}{}{}{}{}{}")
    print(f"Proyecto actual: {project_key}")
    print("{}{}{}{}{}{}{}")
    
    sonar_project = project_key.split('_')[1]
    
    salir = False
    pagina = 1
    now = 0
    
    
    failed_attempts1 = 0
    failed_attempts2 = 0
    failed_attempts3 = 0
    failed_attempts4 = 0  
    success = 0
  
    # Make a GET request to the SonarCloud API to retrieve issues
    tags = properties.get("issueTags").data.strip()
    language = properties.get("language").data.strip()
    print(f"Processing issues - tag: {tags}")
    while(salir == False):
      sonar_request = f"https://sonarcloud.io/api/issues/search?componentKeys={project_key}&languages={language}&tags={tags}&ps=100&p={pagina}&token={api_token}"
      sonar_response = requests.get(sonar_request)
      
      # Parse the JSON response
      issues = json.loads(sonar_response.text)["issues"]
      total = json.loads(sonar_response.text)["total"]
      if(total > 100):
        now = pagina*100
        if(total <= now):
          salir = True
      else:
        salir = True
      pagina = pagina+1
      
      print(len(issues))
      
      # Iterate over the issues and generate refactored code
      for issue in issues:
        result = processIssues(issue, sonar_project, properties, model, model_type, sleep_time)
      
        match result:
          case -4:
            failed_attempts4 = failed_attempts4 + 1  
          case -3:
            failed_attempts3 = failed_attempts3 + 1
          case -2:
            failed_attempts2 = failed_attempts2 + 1
          case -1:  
            failed_attempts1 = failed_attempts1 + 1
          case 0:
            success = success + 1
              
    
    printTotalResults(failed_attempts1, failed_attempts2, failed_attempts3, failed_attempts4, success)
    end = time.time()
    total_time = int(end - start)
    print(f"Tiempo de ejecucion = {total_time}")        
  
  
  
main()
