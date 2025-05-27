// Sends a test report to Bitbucket Cloud API. Testmode can either be EditMode or PlayMode.
def sendTestReport(workspace, reportDir, commitHash) {
    sh "python \'${workspace}/python/create_bitbucket_test_report.py\' \'${commitHash}\' \'${reportDir}\'"
}

// Parses the given log for any errors recorded in a text file of known errors. Not currently in use.
def parseLogsForError(logPath) {
    return sh (script: "python \'${workspace}/python/get_unity_failure.py\' \'${logPath}\'", returnStdout: true)
}

// Checks if an exit code thrown during a test stage should fail the PR Pipeline. ExitCode 2 means failing tests, which we want to report back to Bitbucket
// without failing the entire pipeline. *NOTE POTENTIALLY UNUSED*
def checkIfTestStageExitCodeShouldExit(workspace, exitCode) {
    if (exitCode == 3 || exitCode == 1) {
        sh "exit ${exitCode}"
    }
}

// Checks if a Unity executable exists and returns its path. Downloads the missing Unity version if not installed.
def getUnityExecutable(workspace, projectDir) {
    try {
        def unityExecutable = sh(script: "python '${workspace}/python/get_unity_version.py' '${projectDir}' executable-path", returnStdout: true).trim()
        if (!fileExists(unityExecutable)) {
            def version = sh(script: "python '${workspace}/python/get_unity_version.py' '${projectDir}' version", returnStdout: true).trim()
            def revision = sh(script: "python '${workspace}/python/get_unity_version.py' '${projectDir}' revision", returnStdout: true).trim()

            echo "Unity Editor version ${version} not found. Attempting installation..."
            def installCommand = "\"C:\\Program Files\\Unity Hub\\Unity Hub.exe\" -- --headless install --version ${version} --changeset ${revision}"
            def exitCode = sh(script: installCommand, returnStatus: true)
            if (exitCode != 0) {
                error("Failed to install Unity Editor version ${version}.")
            }

            echo "Installing WebGL Build Support..."
            def webglInstallCommand = "\"C:\\Program Files\\Unity Hub\\Unity Hub.exe\" -- --headless install-modules --version ${version} -m webgl"
            exitCode = sh(script: webglInstallCommand, returnStatus: true)
            if (exitCode != 0) {
                error("Failed to install WebGL Build Support for Unity version ${version}.")
            }
        }
        return unityExecutable
    } catch (Exception e) {
        error("An error occurred while retrieving or installing Unity executable: ${e.getMessage()}")
    }
}

// Runs a Unity project's tests of a specified type, while also allowing optional code coverage and test reporting.
def runUnityTests(unityExecutable, reportDir, projectDir, testType, enableReporting, deploymentBuild) {
    //setup for commands/executable
 
    def logFile = "${reportDir}/test_results/${testType}-tests.log"
 
    def reportSettings = ""
    
    if(enableReporting){
        reportSettings = """ \
        -testResults \"${reportDir}/test_results/${testType}-results.xml\" \
        -debugCodeOptimization \
        -enableCodeCoverage \
        -coverageResultsPath \"${REPORT_DIR}/coverage_results\" \
        -coverageOptions \"useProjectSettings\""""
    }else{
        reportSettings = """ \
        -testResults \"${reportDir}/test_results/${testType}-results.xml\" \
        -debugCodeOptimization"""
    }
 
    def flags = "-projectPath \"${projectDir}\" \
        -batchmode \
        -testPlatform ${testType} \
        -runTests \
        -logFile \"${logFile}\"${reportSettings}"
 
    // Allows only PlayMode to run with graphics enabled
    if(testType == "EditMode"){
        flags += " -nographics"
    }
 
    if(testType == "PlayMode"){
        flags += " -testCategory BuildServer"
    }
 
    echo "Flags set to: ${flags}"
 
    def exitCode = sh (script: """\"${unityExecutable}\" \
        ${flags}""", returnStatus: true)
 
    if ((exitCode != 0)) {
        if(deploymentBuild){
            error("Test failed with exit code ${exitCode}. Check the log file for more details.")
            sh "exit ${exitCode}"
        }
        catchError(buildResult: 'FAILURE', stageResult: 'FAILURE'){
            error("Test failed with exit code ${exitCode}. Check the log file for more details.")
        }
    }
}

// Converts a Unity test result XML file to an HTML file.
def convertTestResultsToHtml(reportDir, testType) {
    // Writing the console output to a file because Jenkins' returnStdout still causes the pipeline to fail if the exit code != 0
    def exitCode = sh (script: """dotnet C:/UnityTestRunnerResultsReporter/UnityTestRunnerResultsReporter.dll \
        --resultsPath=\"${reportDir}/test_results\" \
        --resultXMLName=${testType}-results.xml \
        --unityLogName=${testType}-tests.log \
        --reportdirpath=\"${reportDir}/test_results/${testType}-report\" > UnityTestRunnerResultsReporter.log""", returnStatus: true)
    
    // This Unity tool throws an error if any tests are failing, yet still generates the report.
    // If the tests are failing, we want to avoid failing the pipeline so we can access the report.
    if (exitCode != 0) {
        consoleOutput = readFile("UnityTestRunnerResultsReporter.log")
        def testReportGenerated = consoleOutput =~ /Test report generated:/

        if (!testReportGenerated) {
            println "Error: Test report was not generated for ${testType}. Exit code: ${exitCode}"
            println "Log Output: ${consoleOutput}"
            sh "exit 1"
        }
    }
}

// Builds a Unity project.
def buildProject(reportDir, projectDir, unityExecutable) {
    def logFile = "${reportDir}/build_project_results/build_project.log"

    def exitCode = sh (script:"""\"${unityExecutable}\" \
        -quit \
        -batchmode \
        -nographics \
        -projectPath \"${projectDir}\" \
        -logFile \"${logFile}\" \
        -buildTarget WebGL \
        -executeMethod Builder.BuildWebGL""", returnStatus: true)

    if (exitCode != 0) {
        sh "exit ${exitCode}"
    }
}

// A method for post-build PR actions.
// Creates a log report for Unity logs and Jenkins logs, then publishes it to the web server,
// and lastly sends the build status to Bitbucket.
def postBuild(status) {
    sh "python -u \'${env.WORKSPACE}/python/create_log_report.py\'"

    sh """ssh vconadmin@dlx-webhost.canadacentral.cloudapp.azure.com \
    \"sudo mkdir -p /var/www/html/${env.FOLDER_NAME}/Reports/${env.TICKET_NUMBER} \
    && sudo chown vconadmin:vconadmin /var/www/html/${env.FOLDER_NAME}/Reports/${env.TICKET_NUMBER}\""""

    if (fileExists("${env.REPORT_DIR}/logs.html")) {
        sh "scp -i C:/Users/ci-catherine/.ssh/vconkey1.pem -rp \"${env.REPORT_DIR}/logs.html\" \
    \"vconadmin@dlx-webhost.canadacentral.cloudapp.azure.com:/var/www/html/${env.FOLDER_NAME}/Reports/${env.TICKET_NUMBER}\""
    }
}

return this