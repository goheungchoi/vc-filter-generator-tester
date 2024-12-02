import os
import sys
import uuid
import argparse
import xml.etree.ElementTree as ET
import re

# Register default namespace
namespace = 'http://schemas.microsoft.com/developer/msbuild/2003'
ET.register_namespace('', namespace)

ignores: set[str] = set({r"\.vs", r"x86", r"x64", r"out", r"[Bb]uild", r"[Dd]ebug", r"[Rr]elease", r".*\.vcxproj", r".*\.vcxproj.filters", r".*\.vcxproj.user"})

def convert_to_regex(set: set[str]) -> str:
    # Escape special regex characters and join with '|'
    regex = '|'.join(set)
    return regex

def find_vcx_project(dir:str):
  proj_name:str = ""
  proj_file:str = ""

  # Find the vcx project file
  for file in os.listdir(dir):
    # print(file)
    if file.endswith('.vcxproj'):
      proj_file = file
      proj_name = file.rsplit('.', 1)[0]
      print(f"VC Project found: {proj_name}")
        
  if proj_name == "":
    print("VC Project not found.")
    exit(1)

  return proj_name, proj_file

def open_vc_filter_xml(proj_filters_file:str):
  try:
    proj_filters_xml = ET.parse(proj_filters_file)
  except FileNotFoundError:
    print(f"Filters file not found: {proj_filters_file}")
    print(f"Generating a filter file.")
    root = ET.Element(f"{{{namespace}}}Project", {"ToolsVersion": "4.0"})
    ET.SubElement(root, f"{{{namespace}}}ItemGroup")
    ET.SubElement(root, f"{{{namespace}}}ItemGroup")
    proj_filters_xml = ET.ElementTree(root)
  
  return proj_filters_xml

def main():
  # Parse argument
  parser = argparse.ArgumentParser(prog="generate-filters", 
                                   description="Generate VC project filters")
  parser.add_argument("cwd", nargs='?', default=os.curdir, type=str)
  parser.add_argument("-E", "--exclude", action="extend", nargs="+", type=str)

  args = parser.parse_args()

  cwd:str = args.cwd

  # Update the ignore list if exclude flag is used
  if args.exclude != None:
    ignores.update(args.exclude)

  re_ignores = re.compile(convert_to_regex(ignores))

  proj_name, proj_file = find_vcx_project(cwd)
  proj_filters_file = proj_file + '.filters'

  # print(proj_name, proj_file)

  # Open the project xml and filters xml
  proj_xml = ET.parse(proj_file)
  proj_filters_xml = open_vc_filter_xml(proj_filters_file)

  namespace = {'ns': 'http://schemas.microsoft.com/developer/msbuild/2003'}
  root = proj_filters_xml.getroot()

  item_list = root.findall('ns:ItemGroup', namespace)
  
  filters: set[str] = set()
  compile_targets: dict[str, str] = {}
  for item in item_list[0]:
    filters.add(item.get("Include"))

  for item in item_list[1]:
    target_dir = item.find('ns:Filter', namespace)
    if target_dir != None:
      compile_targets[item.get("Include")] = target_dir.text
    else:
      compile_targets[item.get("Include")] = None

  # print(filters)
  # print(compile_targets)

  # print("\n")

  # Get the file tree
  actual_filters: set[str] = set()
  actual_compile_targets: dict[str, str] = {}
  for root, dirs, files in os.walk(cwd):
    root = root.removeprefix('.').removeprefix('\\')

    # exclude the directory in the exclude list
    # if re_ignores.search(root):
    #   continue
    
    dirs[:] = [d for d in dirs if not re_ignores.match(d)]

    for dir in dirs:
      # Skip the excluse dir
      # if re_ignores.search(dir):
      #   continue
      full_dir = os.path.join(root, dir)
      actual_filters.add(full_dir)

    for file in files:
      # Skip the exclude files
      if re_ignores.match(file):
        continue

      #if file.endswith((".c", ".cpp", ".h", ".hpp")):
      full_file_path = os.path.join(root, file)
      if root == "":
        actual_compile_targets[full_file_path] = None
      else:
        actual_compile_targets[full_file_path] = root
  
  # print(actual_filters)
  # print(actual_compile_targets)

  # Remove unnecessary filters and targets
  unnecessary_filters = filters.difference(actual_filters)
  for item in item_list[0][:]:
    if item.get("Include") in unnecessary_filters:
      item_list[0].remove(item)
  
  # print()

  compile_target_paths = set(compile_targets.keys())
  # print("compile_target_paths: ", compile_target_paths)
  actual_compile_target_paths = set(actual_compile_targets.keys())
  # print("actual_compile_target_paths", actual_compile_target_paths)
  existing_compile_target_paths = compile_target_paths.intersection(actual_compile_target_paths)
  # print("existing_compile_target_paths", existing_compile_target_paths)
  new_compile_target_paths = actual_compile_target_paths.difference(existing_compile_target_paths)
  # print("new_compile_target_paths", new_compile_target_paths)
  # print()

  unnecessary_compile_targets = compile_target_paths.difference(existing_compile_target_paths)
  for item in item_list[1][:]:
    if item.get("Include") in unnecessary_compile_targets:
      item_list[1].remove(item)

  # Add new filters and targets
  for filter in actual_filters:
    if filter in filters:
      continue
    else:
      elem = ET.Element("Filter")
      elem.set("Include", filter)
      id = ET.SubElement(elem, "UniqueIdentifier")
      id.text = '{' + str(uuid.uuid4()).upper() + '}'
      item_list[0].append(elem)

  # Check the compile targets existing in both actual and old
  for item in item_list[1]:
    item_include = item.get("Include")
    if item_include in existing_compile_target_paths:
      value = actual_compile_targets[item_include]

      filter_elem = item.find('ns:Filter', namespace)
      if filter_elem == None and value == None:
        continue
      elif filter_elem == None and value != None:
        elem = ET.Element("Filter")
        elem.text = actual_compile_targets[item_include]
        item.append(elem)
      elif filter_elem != None and value == None:
        item.remove(filter_elem)
      else:
        if filter_elem.text != value:
          filter_elem.text = value
  
  for new_compile_target_path in new_compile_target_paths:
    if new_compile_target_path.endswith((".c", ".cc", ".cpp")):
      elem = ET.Element("ClCompile")
      elem.set("Include", new_compile_target_path)
    elif new_compile_target_path.endswith((".h", ".hpp")):
      elem = ET.Element("ClInclude")
      elem.set("Include", new_compile_target_path)
    else:
      elem = ET.Element("None")
      elem.set("Include", new_compile_target_path)

    if actual_compile_targets[new_compile_target_path] != None:
      filter = ET.SubElement(elem, "Filter")
      filter.text = actual_compile_targets[new_compile_target_path]
    item_list[1].append(elem)

  # Add compile targets to the project file
  proj_item_groups = proj_xml.getroot().findall('ns:ItemGroup', namespace)

  # Clear all targets except for the project config and project ref
  for item_group in proj_item_groups[:]:
    if item_group.get('Label') != None and item_group.get('Label') == 'ProjectConfigurations':
      continue
    elif item_group.find('ns:ProjectReference', namespace) != None:
      continue
    else:
      proj_xml.getroot().remove(item_group)
  
  # Add new targets
  new_item_group = ET.Element("ItemGroup")
  for compile_target_path in sorted(actual_compile_target_paths):
    if compile_target_path.endswith((".c", ".cc", ".cpp")):
      elem = ET.SubElement(new_item_group, "ClCompile")
      elem.set("Include", compile_target_path)
    elif compile_target_path.endswith((".h", ".hpp")):
      elem = ET.SubElement(new_item_group, "ClInclude")
      elem.set("Include", compile_target_path)
    else:
      elem = ET.SubElement(new_item_group, "None")
      elem.set("Include", compile_target_path)

  proj_xml.getroot().append(new_item_group)

  # Output results
  ET.indent(proj_xml, space="\t", level=0)
  ET.indent(proj_filters_xml, space="\t", level=0)
  proj_xml.write(proj_file, 'utf-8', True)
  proj_filters_xml.write(proj_filters_file, 'utf-8', True)

  #proj_xml.write('proj_test.xml', 'utf-8', True)
  #proj_filters_xml.write('proj_filters_test.xml', 'utf-8', True)

if __name__ == "__main__":
  main()
