import os
import math
import xml.dom.minidom
import glob
import subprocess
import threading
import time
import codecs
import numpy as np
import datetime

class Command(object):
	def __init__(self, cmd, processes):
		self.cmd = cmd
		self.processes = processes
		self.process = None

	def run(self, timeout):
		def target():
			self.process = subprocess.Popen(self.cmd, shell=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
			self.process.communicate()

		thread = threading.Thread(target=target)
		thread.start()

		thread.join(timeout)
		if thread.is_alive():
			print 'Terminating process'
			self.KillProcessCmd(self.processes)
			self.process.terminate()
			thread.join()
		print self.process.returncode
		return self.process.returncode

	def KillProcessCmd(self, processes):
		for process in processes:
			if os.name == 'nt':
				os.system('taskkill /f /im \"' + process + '*\"')
				os.system('tskill \"' + process + '*\"')
			elif os.name == 'posix':
				cmd = 'killall -9 \"' + process + '\"'
				print cmd
				p = subprocess.Popen(["killall", "-9", process], stdin=subprocess.PIPE, stdout=subprocess.PIPE, bufsize=1)

def extractData(fullPath, type):
	dataDict = {}
	dataDictLA = {}
	for fn in glob.glob(fullPath + os.sep + "*"):
		if not os.path.isfile(fn):
			continue

		path, fileName = os.path.split(fn)
		name, ext = os.path.splitext(fileName)
		if ext != ".xml":
			continue

		# right file
		inputDom = xml.dom.minidom.parse(fn)

		inputRootNode = inputDom.documentElement
		errorDeltaValue = "NO_error"
		for subNode in inputRootNode.childNodes:
			# just look at performance data
			nodeTypeName = subNode.nodeName.lower()
			if nodeTypeName not in ('elapsedtime', 'fps', 'framerategraphics'):
				continue
			if subNode.nodeType != subNode.ELEMENT_NODE:
				continue

			desValue = subNode.getAttribute("description")
			if desValue == "Error Delta":
				errorDeltaValue = subNode.getAttribute("value")
				continue

			fullTestName = desValue
			if fullTestName not in dataDict.keys():
				dataDict[fullTestName] = []

			# valuable node
			realValue = subNode.getAttribute("value")
			dataDict[fullTestName].append(float(realValue))

			if type == 'LA':
				if fullTestName not in dataDictLA.keys():
					dataDictLA[fullTestName] = {}
				if nodeTypeName not in dataDictLA[fullTestName].keys():
					dataDictLA[fullTestName][nodeTypeName] = []
				realValue = subNode.getAttribute("value")
				dataDictLA[fullTestName][nodeTypeName].append(float(realValue))
				# delete input dom
		del inputDom

	if type == 'LA':
		return dataDictLA
	else :
		resultList = []
		for tmp in dataDict:
			resultList.append(dataDict[tmp])
		return resultList


def StdMeanRatio(valuelist):
	array = np.array(valuelist)
	ratio = array.std()/array.mean()
	return ratio

def CheckData(exePath, testcase, ntpProject):
	path, fileName = os.path.split(testcase)
	name, ext = os.path.splitext(fileName)

	path, fileName = os.path.split(exePath)
	
	PerfTypeDir = ''
	if ntpProject.lower() == "largeassembly":
		PerfTypeDir = 'Capacity'
	else:
		PerfTypeDir = 'Performance'
	 
	if os.name == 'nt':
		if 'dev' in path or 'staging' in path or 'continuousupdate' in path:
			performanceDir = path.replace('\\', '/') + '/Result/Neutron/Test/'+PerfTypeDir+'/'
		else:
			performanceDir = path.replace('\\', '/') + '/Neutron/Test/'+PerfTypeDir+'/'
	elif os.name == 'posix':
		if 'dev' in exePath or 'staging' in exePath or 'continuousupdate' in exePath:
			performanceDir = os.path.join(os.path.dirname(exePath), 'Libraries', 'Neutron', 'Result', 'Neutron', 'Test', PerfTypeDir)
		else:
			performanceDir = os.path.join(os.path.dirname(exePath), 'Libraries', 'Neutron', 'Neutron', 'Test', PerfTypeDir)
	
	resultDir = None
	list_dirs = os.walk(performanceDir)
	for root, dirs, files in list_dirs:
		for d in dirs:
			if name.lower() == d.lower():
				resultDir = os.path.join(root, d)
				break
	
	if (resultDir == None):
		print "Failed to get result directory for case: " + name
		return True
	data = extractData(resultDir, 'checkdata')
	for tmp in data:
		if (len(tmp) < 3):
			return False
		if (StdMeanRatio(tmp) > 0.04):
			return False
	return True

def RunTestCase(exePath, testcasePath, processes, ntpProject):
	cmd = ''
	if os.name == "nt":
		cmd = '"{0}" -execute "test.run {1} /CloseAfterDone"'.format(exePath, testcasePath)
	elif os.name == 'posix':
		cmd = "open -W \"{0}\" --args nothing -execute \"test.run \\\"{1}\\\" /CloseAfterDone\"".format(exePath, testcasePath)
	print cmd
	
	command = Command(cmd, processes)
	returncode = command.run(timeout=900)

	if returncode != 0:
		GenerateFailureXML(exePath, testcasePath, ntpProject)
	# Kill the Fusion process because test.run cannot kill itself now
	KillProcess(processes)

def GenerateFailureXML(exePath, testcasePath, ntpProject):
	impl = xml.dom.minidom.getDOMImplementation()
	dom = impl.createDocument(None, "Metrics", None)
	dom.version = '1.0'  
	dom.encoding = 'UTF-16'  
	dom.standalone = 'no'
	
	root = dom.documentElement  
	elem = dom.createElement('Fail')
	root.appendChild(elem)
	PerfTypeDir = ''
	if ntpProject.lower() == "largeassembly":
		PerfTypeDir = 'Capacity'
	else:
		PerfTypeDir = 'Performance'
	
	if 'dev' in exePath or 'staging' in exePath or 'continuousupdate' in exePath:
		testcase = testcasePath.split('Neutron/Test/Performance/')[-1].split('.txt')[0]
		if os.name == 'nt':
			resultDir = os.path.join(os.path.dirname(exePath), 'Result', 'Neutron', 'Test', PerfTypeDir)
		elif os.name == 'posix':
			resultDir = os.path.join(os.path.dirname(exePath), 'Libraries', 'Neutron', 'Result', 'Neutron', 'Test', PerfTypeDir)
		caseDir = os.path.join(resultDir, testcase)
		
		print caseDir
		if not os.path.exists(caseDir):
			print "create result directory for failure case if it is not exists"
			os.makedirs(caseDir)

		xmlfile = os.path.join(caseDir, os.path.basename(testcase)+'_'+str(datetime.datetime.now().strftime('%Y%m%d%H%M%S'))+'.xml')
		print xmlfile
		if os.path.exists(xmlfile):
			print "Has the failed xml already!"
			
		with codecs.open(xmlfile, 'w', encoding="utf-16") as f:
			dom.writexml(f,'\n',' ','')
			print "write failed xml"
	else:
		testcase = os.path.basename(testcasePath).split('.txt')[0]
		if os.name == 'nt':
			resultDir = os.path.join(os.path.dirname(exePath), 'Neutron', 'Test', PerfTypeDir)
		elif os.name == 'posix':
			resultDir = os.path.join(os.path.dirname(exePath), 'Libraries', 'Neutron', 'Neutron', 'Test', PerfTypeDir)
		caseDir = os.path.join(resultDir, testcase)

		if not os.path.exists(caseDir):
			os.makedirs(caseDir)

		f = codecs.open(os.path.join(caseDir, testcase+'_'+str(datetime.datetime.now().strftime('%Y%m%d%H%M%S'))+'.xml'), 'w', 'utf-16')
		dom.writexml(f,'\n',' ','')
		f.close()
	

def KillProcess(processes):
	for process in processes:
		if os.name == 'nt':
			os.system('taskkill /f /im \"' + process + '*\"')
			os.system('tskill \"' + process + '*\"')
		elif os.name == 'posix':
			os.system('killall -9 \"' + process + '\"')

def parseNtpFile(exePath, ntpFile):
	scriptList = []
	path, fileName = os.path.split(exePath)

	ntpDom = xml.dom.minidom.parse(ntpFile)
	rootNode = ntpDom.documentElement
	for subNode in rootNode.getElementsByTagName("Item"):
		scriptFile = subNode.getAttribute("ScriptFile")
		name, ext = os.path.splitext(scriptFile)
		if ext != ".txt":
			continue
		if os.name == 'nt':
			scriptList.append(path.replace('\\', '/') + '/' + scriptFile)
		elif os.name == 'posix':
			scriptList.append(os.path.dirname(exePath) + '/Libraries/Neutron/' + scriptFile)

	return scriptList

def RunMgr(exePath, ntpFile, processes,label, ntpProject):
	testCases = parseNtpFile(exePath, ntpFile)
	for i in range(3):
		for testcase in testCases:
			RunTestCase(exePath, testcase, processes, ntpProject)


	for testcase in testCases:
		if (CheckData(exePath, testcase, ntpProject)):
			continue
		else:
			print "Test case {0} is not stable, rerun it".format(testcase)
			for i in range(3):
				RunTestCase(exePath, testcase, processes, ntpProject)
	WriteResultToDB(ntpFile, exePath)

def WriteResultToDB(ntpFile, exePath):
	if 'dev' in exePath or 'staging' in exePath or 'continuousupdate' in exePath:
		if os.name == 'nt':
			resultDir = os.path.join(os.path.dirname(exePath), 'Result', 'Neutron', 'Test', 'Performance')
			cmd = r'python35\win\python CITools\save_performance_test_result_from_dir.py "{0}" "{1}"'.format(ntpFile, resultDir)
		elif os.name == 'posix':
			resultDir = os.path.join(os.path.dirname(exePath), 'Libraries', 'Neutron', 'Result', 'Neutron', 'Test', 'Performance')
			cmd = r'python3 CITools/save_performance_test_result_from_dir.py "{0}" "{1}"'.format(ntpFile, resultDir)
	else:
		if os.name == 'nt':
			resultDir = os.path.join(os.path.dirname(exePath), 'Neutron', 'Test', 'Performance')
			cmd = r'python35\win\python CITools\save_performance_test_result_from_dir.py "{0}" "{1}"'.format(ntpFile, resultDir)
		elif os.name == 'posix':
			resultDir = os.path.join(os.path.dirname(exePath), 'Libraries', 'Neutron', 'Neutron', 'Test', 'Performance')
			cmd = r'python3 CITools/save_performance_test_result_from_dir.py "{0}" "{1}"'.format(ntpFile, resultDir)
	print cmd
	os.system(cmd)


if __name__ == '__main__':
	a = CheckData(r"E:\TESTDATA\NewDesign\production\fusion.exe", r"E:\TESTDATA\NewDesign\Result\Neutron\Test\Performance\Modeling\Image\Fusion_Image_Decal.txt")
	print a
