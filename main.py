import requests
import json
import time
import llm
import sqlite3
import os
import pathlib
import textwrap
import google.generativeai as genai
from dotenv import load_dotenv
from IPython.display import display
from IPython.display import Markdown
from jproperties import Properties

from methodRefactoring import refactorMethod


def loadProperties():
  configs = Properties()
  with open('config_file.properties', 'rb') as config_file:
    configs.load(config_file)
  return configs


def loadFile(path):
  start = False
  comment = False
  skippedLines = 0
  skippedCode = ""
  lines = ""
  try:
    with open(path, "r") as file:
      for line in file:
        if(start):    
          lines += f"{line}"
        else:
          skippedLines = skippedLines + 1
          if(comment and ('*/' in line)):
            skippedCode += f"{line}"
            comment = False
          elif('/*' in line):
            skippedCode += f"{line}"
            comment = True
          elif("package" in line):
            start = True
            lines += f"{line}"
            skippedLines = skippedLines - 1
          else:
            skippedCode += f"{line}"
    return [lines, skippedLines, skippedCode]
  except:
    return ['-1', 0, ""]
  
def writeFile(path, code):
  f = open(path, "w")
  f.write(code)
  f.close()


def getFileLocation(issue_file_location):
  if(properties.get("forcedFile").data == "True"):
    return properties.get("forcedFileRoot").data
  else:
    return issue_file_location


def setLLM(model):
  match model:
    case "gemini":
      GOOGLE_API_KEY = os.environ.get("GEMINI_MODEL_KEY")
      genai.configure(api_key=GOOGLE_API_KEY)
      model = genai.GenerativeModel('gemini-1.5-pro-latest')
    case "GPT-4":
      model = llm.get_model("gpt-4")
      model.key = os.environ.get("LLM_GPT4_MODEL_KEY")
    case "GPT-4-turbo":
      model = llm.get_model("gpt-4-turbo")
      model.key = os.environ.get("LLM_GPT4_MODEL_KEY")
  return model
  
def getIssueType(issue_message):
  ret = ""
  
  if("Cognitive Complexity" in issue_message):
    ret = "cog"
  elif ("Cyclomatic Complexity" in issue_message):
    ret = "method"
  elif (("This method has" in issue_message) and ("lines, which is greater than the" in issue_message) and ("lines authorized. Split it into smaller methods." in issue_message)):
    ret = "method"
  else:
    ret = "other"
    
  return ret



load_dotenv("properties.env")

properties = loadProperties()

# Set your SonarCloud API token and project key
api_token = os.environ.get("SONAR_API_TOKEN")

# Set the LLM model and API key
modelType = "gemini"
model = setLLM(modelType)

# Throttle limit variables
sleep_time = 40

for project_key in properties.get("argoProjectKey").data.split(', '):

  print("{}{}{}{}{}{}{}")
  print(f"Proyecto actual: {project_key}")
  print("{}{}{}{}{}{}{}")
  
  sonar_project = project_key.split('_')[1]
  
  salir = False
  pagina = 1
  now = 0
  
  i = 0
  
  methodAux = 0
  
  failedAttempts1 = 0
  failedAttempts2 = 0
  failedAttempts3 = 0
  failedAttempts4 = 0  
  success = 0

  # Make a GET request to the SonarCloud API to retrieve issues
  while(salir == False):
    sonar_request = f"https://sonarcloud.io/api/issues/search?componentKeys={project_key}&languages=java&tags=brain-overload&ps=100&p={pagina}&token={api_token}"
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
    
    # Iterate over the issues and generate refactored code
    for issue in issues:
        # Get the issue key, line number and refactoring message
        issue_message = issue["message"]
        i = i + 1
        
        issue_type = getIssueType(issue_message)
    
        if(issue_type == "cog"):
          issue_location = issue['component'].split(':')[1]
          original_issue_line = issue["line"]
          issue_file_location = f"{sonar_project}/{issue_location}"
          
          file_location = getFileLocation(issue_file_location)
          refactoring_file_location = f"refactoredProjects/{file_location}"
          original_file_location = f"originalProjects/{file_location}"
          database_location = f"resultsDatabases/{file_location}"
          
          # Extract the code from the file that is going to be refactored and number the lines for the future prompts
          [code, skippedLines, skippedCode] = loadFile(original_file_location)          
          
          # Get the code snippet
          if((code != '-1') and (len(code) < 60000)): 
            methodAux = methodAux + 1 
            #print(f"Detected issue {i}: {issue}.")
            print(f"Detected issue {i}")    
            print(f"Issue message: {issue_message}")  
            print(f"Issue line: {original_issue_line}")
            print(f"Skipped lines: {skippedLines}")
            
            refactoredFile = refactorMethod(code, issue, skippedLines, skippedCode, sonar_project, model, modelType, sleep_time)
            
            if(refactoredFile == '-1'):
              failedAttempts1 = failedAttempts1 + 1
            elif(refactoredFile == '-2'):
              failedAttempts2 = failedAttempts2 + 1
            elif(refactoredFile == '-3'):
              failedAttempts3 = failedAttempts3 + 1
            elif(refactoredFile == '-4'):
              failedAttempts4 = failedAttempts4 + 1
            else:
              success = success + 1
              writeFile(refactoring_file_location, refactoredFile)
            
  print(f"---------------------------------------------------------------------------------")
  print(f"Numbering lines errors: {failedAttempts1}")
  print(f"LLM errors: {failedAttempts2}")
  print(f"Formating errors: {failedAttempts3}")
  print(f"Applying errors: {failedAttempts4}")
  print(f"---------------------------------------------------------------------------------")
  print(f"Successes: {success}")
  print(methodAux)
  print(i)


