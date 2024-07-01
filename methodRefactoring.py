import re
import os
import sqlite3
import time
from dotenv import load_dotenv
import google.generativeai as genai

def updateDatabase(issue_key, issue_message, sonar_project, issue_file_location, issue_method, original_issue_line, refactoring_result):
  try:
    conn = sqlite3.connect(f'resultados_{sonar_project}_llm.db')
    print(f"Conexion establecida con la base de datos")
    cursor = conn.cursor()
    cursor.execute('''CREATE TABLE IF NOT EXISTS resultados(
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      issue_key TEXT,
      issue_message TEXT,
      issue_project TEXT,
      issue_file_location TEXT,
      issue_method TEXT,
      issue_line INTEGER,
      refactored_code TEXT
      )''')
    cursor.execute('''INSERT INTO resultados(issue_key, issue_message, issue_project, issue_file_location, issue_method, issue_line, refactored_code)
      VALUES(?, ?, ?, ?, ?, ?, ?)''', (issue_key, issue_message, sonar_project, issue_file_location, issue_method, original_issue_line, refactoring_result))
    conn.commit()
  except Exception as error:
    print(f"Algo ha ido mal en la conexion a la BBDD: {error}")
  finally:
    conn.close()
    print(f"Consexion con la base de datos finalizada")

      
def numberCode(code, issue_line):
  numbered_code = ""
  line_number = 1
  for line in code.split('\n'):
    numbered_code += f"{line_number}. {line.strip()}\n"
    if(line_number == issue_line):
      issue_method = line
    line_number += 1
  return [numbered_code, issue_method]

      
def loadSupport(path):
  lines = ""
  with open(path, "r") as file:
    for line in file:
      lines += f"{line}"
  return lines

def refactorMethod(code, issue, skippedLines, skippedCode, sonar_project, model, modelType, sleep_time):
  issue_key = issue["key"]
  original_issue_line = issue["line"]
  adapted_issue_line = original_issue_line - skippedLines
  issue_message = issue["message"]
  issue_location = issue['component'].split(':')[1]
  issue_file_location = f"{sonar_project}/{issue_location}"
  
  time.sleep(sleep_time)
  
  # Extract the information of the support file, which will be given to the LLM in order to get a controlled response
  support_file = loadSupport(os.environ.get("DIRECTORY_SUPPORT_FILE"))
        
  try:
    [numbered_code, issue_method] = numberCode(code, adapted_issue_line)
  except:
    return '-1'

  # Prepare the promtps: \
  # the support prompt to estalish the response format \
  # the standard prompt to get the actual refactoring response \
  # the method line prompt that will return the last line of the refactored method
  support_prompt = f"Within this conversation, when specified only to return the refactored code, I'd like that all the responses regarding refactoring have a structure similiar to the following one:\n{support_file}"
  prompt = f"The method '{issue_method}' in the line {adapted_issue_line} has the following refactoring issue: {issue_message} Refactor only said method to solve the issue. Return only the refactored java code.\n{numbered_code}"
  prompt_lines = f"What is the last line number in the method '{issue_method}'? The answer must exclusively contain the integer."
  
  # Make the prompts to the LLMs
  try:
    if("GPT" in modelType):
      print('a')
      chat = model.conversation()
      chat.prompt(support_prompt)
      response = chat.prompt(prompt).text()
      method_line_number_response = chat.prompt(prompt_lines).text()
    elif("gemini" in modelType):
      chat = model.start_chat(history=[])
      chat.send_message(support_prompt)
      response = chat.send_message(prompt).text
      method_line_number_response = chat.send_message(prompt_lines).text
    else:
      return '-2'
  except:
    return '-2'
  
  try:
    # Format the respones in order to get maneuverable data using a regex
    response_pattern = r"```java\s*(.*?)\s*```"
    response_formated = re.findall(response_pattern, response, re.DOTALL)
    
    # Obtain the method line
    method_line_number = re.search(r'\d+', method_line_number_response).group()
  except:
    return '-3'
  
  # Join the formated respones with the original code, to get the refactored file
  #print(method_line_number)
  try:
    splited_code = code.split('\n')
    splited_formated_response = response_formated[0].strip().split('\n')
    print(f"code: {adapted_issue_line-1}; {splited_code[adapted_issue_line-1]}")
    print(f"code: {adapted_issue_line}; {splited_code[adapted_issue_line]}")
    print(f"refactored: {splited_formated_response[0]}")
    # Remove the headers from the code, so that the merge is successful
    while(splited_code[adapted_issue_line-1].strip() != splited_formated_response[0].strip()):
      del splited_formated_response[0]
      print(f"refactored: {splited_formated_response[0]}")
    del splited_formated_response[0]
    splited_code[adapted_issue_line:int(method_line_number)] = splited_formated_response
    refactoring_result = skippedCode + '\n'.join(splited_code)
    
    # Update the database with the refactoring result
    updateDatabase(issue_key, issue_message, sonar_project, issue_file_location, issue_method, original_issue_line, refactoring_result)
  except:
    return '-4'
  
  return refactoring_result
