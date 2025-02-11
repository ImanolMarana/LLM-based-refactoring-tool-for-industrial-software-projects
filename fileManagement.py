from jproperties import Properties

def getFileLocation(properties, issue_file_location):
  if(properties.get("forcedFile").data == "True"):
    return properties.get("forcedFileRoot").data
  else:
    return issue_file_location



def loadProperties():
  configs = Properties()
  with open('config_file.properties', 'rb') as config_file:
    configs.load(config_file)
  return configs
  
  
  
def loadJavaFile(path):
  start = False
  comment = False
  skipped_lines = 0
  skipped_code = ""
  lines = ""
  try:
    with open(path, "r") as file:    
      for line in file:
        if(start):    
          lines += f"{line}"
        else:
          skipped_lines = skipped_lines + 1
          if(comment and ('*/' in line)):
            skipped_code += f"{line}"
            comment = False
          elif('/*' in line):
            skipped_code += f"{line}"
            comment = True
          elif(not(comment) and ("package" in line)):
            start = True
            lines += f"{line}"
            skipped_lines = skipped_lines - 1
          else:
            skipped_code += f"{line}"
    return [lines, skipped_lines, skipped_code]
  except:
    return ['-1', 0, ""]
    
    
    
def loadOtherFile(path):
  lines = ""
  with open(path, "r") as file:
    for line in file:
      lines += f"{line}"
  return [lines, 0, ""] 
    


def loadFile(path):
  lines = ""
  with open(path, "r") as file:
    for line in file:
      lines += f"{line}"
  return lines
    
    
    
def writeFile(path, code):
  f = open(path, "w")
  f.write(code)
  f.close()
