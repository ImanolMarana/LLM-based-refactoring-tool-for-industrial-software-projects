import re
import os
import sqlite3
import time

from dotenv import load_dotenv
from fileManagement import loadProperties, loadFile

import google.generativeai as genai
import anthropic

def updateDatabase(data, db_path):
  try:
    conn = sqlite3.connect(fr'{db_path}/resultados_{data[2]}_llm_{data[9]}.db')
    print(f"Conexion establecida con la base de datos")
    cursor = conn.cursor()
    cursor.execute('''CREATE TABLE IF NOT EXISTS resultados(
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      issue_key TEXT,
      issue_message TEXT,
      issue_project TEXT,
      issue_file_location TEXT,
      original_code TEXT,
      issue_method TEXT,
      issue_line INTEGER,
      refactored_code TEXT,
      model TEXT
      )''')
    cursor.execute('''INSERT INTO resultados(issue_key, issue_message, issue_project, issue_file_location, original_code, issue_method, issue_line, refactored_code, model)
      VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?)''', (data[0], data[1], data[2], data[3], data[4], data[5], data[6], data[7], data[8]))
    conn.commit()
    ret = "SUCCESS"
  except Exception as error:
    print(f"Algo ha ido mal en la conexion a la BBDD: {error}")
    ret = "ERROR"
  finally:
    conn.close()
    print(f"Consexion con la base de datos finalizada")
    return ret


      
def numberCode(code, issue_line):
  numbered_code = ""
  line_number = 1
  for line in code.split('\n'):
    numbered_code += f"{line_number}. {line.strip()}\n"
    if(line_number == issue_line):
      issue_method = line
    line_number += 1
  return [numbered_code, issue_method]
  
  
  
def requestLLMs(model, model_type, support_file, issue_method, adapted_issue_line, issue_message, numbered_code, sleep_time):
  # Prepare the promtps: \
  # the support prompt to estalish the response format \
  # the standard prompt to get the actual refactoring response \
  # the method line prompt that will return the last line of the refactored method
  support_prompt = f"Within this conversation, when specified only to return the refactored code, I'd like that all the responses regarding refactoring have a structure similar to the following one:\n{support_file}"
  prompt = f"The method '{issue_method}' in the line {adapted_issue_line} has the following refactoring issue: {issue_message} Refactor only said method to solve the issue. Return only the refactored java code.\n{numbered_code}"
  prompt_lines = f"What is the last line number in the method '{issue_method}'? The answer must exclusively contain the integer."
  
  refactoring_response = ""
  method_line_number_response = ""
  
  # Make the prompts to the LLMs
  try:
    time.sleep(int(sleep_time))
  
    if("GPT" in model_type):
      chat = model.conversation()
      sistem = chat.prompt(support_prompt)
      refactoring_response = chat.prompt(prompt).text()
      method_line_number_response = chat.prompt(prompt_lines).text()
      
    elif("gemini" in model_type):
      chat = model.start_chat(history=[])
      chat.send_message(support_prompt)
      refactoring_response = chat.send_message(prompt).text
      method_line_number_response = chat.send_message(prompt_lines).text
      
    elif("claude" in model_type):
      prompts = model[0].messages.create(
        model=model[1],
        max_tokens=8192,
        system=support_prompt,
        messages=[
          {"role":"user", "content":prompt_lines},
          {"role":"user", "content":prompt}
        ]
      )
      
      raw_responses = prompts.content[0].text
      responses = raw_responses.split("\n\n", 1)
      refactoring_response = str(responses[1])
      method_line_number_response = str(responses[0])
      
    else:
      refactoring_response = "error"
      method_line_number_response = 0
      
    return [refactoring_response, method_line_number_response]
    
  except Exception as e:
    print(e)
    return ["error", 0]
    
    

def applyRefactoring(code, response_formated, adapted_issue_line, method_line_number, skipped_code):
  try:
    splited_code = code.split('\n')
    splited_formated_response = response_formated.strip().split('\n')
    print(f"code: {adapted_issue_line-1}; {splited_code[adapted_issue_line-1]}")
    print(f"code: {adapted_issue_line}; {splited_code[adapted_issue_line]}")
    print(f"refactored: {splited_formated_response[0]}")
    # Remove the headers from the code, so that the merge is successful
    while(splited_code[adapted_issue_line-1].strip() != splited_formated_response[0].strip()):
      del splited_formated_response[0]
      print(f"refactored: {splited_formated_response[0]}")
    del splited_formated_response[0]
    splited_code[adapted_issue_line:int(method_line_number)] = splited_formated_response
    refactoring_result = skipped_code + '\n'.join(splited_code)
    return refactoring_result
  except Exception as e:
    print(e)
    return "ERROR"

  

def refactorMethod(code, issue, skipped_lines, skipped_code, sonar_project, model, model_type, sleep_time):

  properties = loadProperties()

  issue_key = issue["key"]
  original_issue_line = issue["line"]
  #original_issue_line = issue["textRange"]["startLine"]  
  adapted_issue_line = original_issue_line - skipped_lines
  issue_message = issue["message"]
  issue_location = issue['component'].split(':')[1]
  issue_file_location = f"{sonar_project}/{issue_location}"
  
  # Extract the information of the support file, which will be given to the LLM in order to get a controlled response
  support_file_path = properties.get("supportFilePath").data
  support_file = loadFile(support_file_path)
        
  [numbered_code, issue_method] = numberCode(code, adapted_issue_line)
    
  [refactoring_response, method_line_number_response] = requestLLMs(model, model_type, support_file, issue_method, adapted_issue_line, issue_message, numbered_code, sleep_time)
  if(refactoring_response == "error"):
    return [-1, ""]
  
  try:
    # Format the respones in order to get maneuverable data using a regex
    response_pattern = r"```java\s*(.*?)\s*```"
    response_formated = re.findall(response_pattern, refactoring_response, re.DOTALL)
    
    # Obtain the method line
    method_line_number = re.search(r'\d+', method_line_number_response).group()
  except Exception as e:
    print(e)
    print("!!!!!!!")
    print("Obtencion manual de la recomendacion")
    print(refactoring_response)
    print("Path")
    print(issue_file_location)
    print(original_issue_line)
    print("!!!!!!!")
    return [-2, ""]
  
  # Join the formated respones with the original code, to get the refactored file
  # print(method_line_number)
  refactoring_result = applyRefactoring(code, response_formated[0], adapted_issue_line, method_line_number, skipped_code)
  if(refactoring_result == "ERROR"):
    print("Obtencion manual de la recomendacion")
    print(refactoring_response)
    return [-3, ""]
    
  # Update the database with the refactoring result
  db_path = properties.get("dbPath").data  
  refactoring_data = [issue_key, issue_message, sonar_project, issue_file_location, code, issue_method, original_issue_line, refactoring_result, str(model), model_type]
  status = updateDatabase(refactoring_data, db_path)
  if(status == "ERROR"):
    return [-4, ""]
  
  return [0, refactoring_result]
