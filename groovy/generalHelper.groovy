// Clones or updates a repository in the specified directory.
// If the directory exists and is a valid git repository, it fetches the latest changes.
// Otherwise, it clones the repository from scratch.
def cloneOrUpdateRepo(String projectDir, String repoSsh, String branch) {
    if (!projectDir || !repoSsh || !branch) {
        error "Missing required parameters for cloneOrUpdateRepo()"
    }

    echo "Checking if the project directory exists..."
    if (!new File(projectDir).exists()) {
        echo "Cloning repository..."
        sh "git clone ${repoSsh} \"${projectDir}\""
    } else {
        if (new File("${projectDir}/.git").exists()) {
            echo "Project already exists. Fetching latest changes..."
            dir(projectDir) {
                echo "Current branch before checkout:"
                sh "git branch --show-current"

                // Remove lock file if it exists
                sh "rm -f '.git/index.lock'"
                sh "git fetch origin"

                // Check if the branch exist or not
                // And then check out to the PR branch
                checkoutBranch(projectDir, branch);

                echo "Current branch after checkout:"
                sh "git branch --show-current"

                sh "git pull"
            }
        } else {
            echo "Invalid git repository. Cleaning up and cloning afresh..."
            sh "rm -rf '${projectDir}'"
            sh "git clone ${repoSsh} \"${projectDir}\""
        }
    }
}

def getDefaultBranch() {
    // Use git remote show to get the default branch
    def defaultBranch = sh(script: "git remote show origin | grep 'HEAD branch' | awk '{print \$NF}'", returnStdout: true).trim()
    if (!defaultBranch) {
        error "Failed to determine the default branch from the remote repository."
    }
    echo "Default branch is determined to be '${defaultBranch}'."
    return defaultBranch
}



def initializeEnvironment(String workspace, String commitHash, String prBranch, String projectDir) {
    echo "Sending 'In Progress' status to Bitbucket..."
    sendBuildStatus(workspace, "INPROGRESS", commitHash)
    env.TICKET_NUMBER = parseTicketNumber(prBranch)
    env.FOLDER_NAME = "${JOB_NAME}".split('/').first()
}

def checkoutBranch(String projectDir, String targetBranch) {
    dir(projectDir) {
        echo "Checking out branch ${targetBranch}..."
        def branchExists = sh(script: "git show-ref --verify --quiet refs/heads/${targetBranch} || git show-ref --verify --quiet refs/remotes/origin/${targetBranch}", returnStatus: true) == 0
        if (!branchExists) {
            error "Branch ${targetBranch} does not exist locally or remotely."
        }
        // Clean up added and modified before checkout
        sh "git reset --hard"
        // Clean up all untracked files before checkout
        sh "git clean -fd"
        // checkout
        sh "git checkout ${targetBranch}"
    }
}


// This will try to merge the branch, throwing an error if theres an error.
def mergeBranchIfNeeded() {
    def destinationBranch = getDefaultBranch()
    try {
        echo "Fetching latest changes from origin..."
        sh "git fetch origin"

        // Check if the destination branch exists remotely
        def branchExists = sh(script: "git show-ref --verify --quiet refs/remotes/origin/${destinationBranch}", returnStatus: true) == 0
        if (!branchExists) {
            error "Branch ${destinationBranch} does not exist in the remote repository."
        }

        // Check if the branch is up-to-date
        echo "Checking if branch is up-to-date with ${destinationBranch}..."
        if (isBranchUpToDate(destinationBranch) == 0) {
            echo "Branch is up-to-date with ${destinationBranch}."
            return
        }

        echo "Branch is not up-to-date. Attempting to merge ${destinationBranch}..."
        if (tryMerge(destinationBranch) == 0) {
            echo "Merge completed successfully."
        } else {
            echo "Merge conflicts detected. Aborting the merge."
            sh "git merge --abort || true" // Safely abort merge if one is in progress
            error("Merge process failed.")
        }
    } catch (Exception e) {
        echo "An error occurred during the merge process: ${e.getMessage()}"
        error("Merge process failed.")
    }
}

def validateCommitHashes(String workspace, String projectDir, String prCommit, String testRunFlag) {
    def commitHash = getFullCommitHash(workspace, prCommit)
    dir(projectDir) {
        def currentHash = getCurrentCommitHash()
        echo "Current Commit Hash: ${currentHash}, Target Commit Hash: ${commitHash}"
        if (isEqualCommitHash(currentHash, commitHash) && !testRunFlag.equals("Y")) {
            def message = "No commits updated. Exiting the pipeline..."
            echo message
            currentBuild.result = 'ABORTED'
            error(message)
        }
    }
    return commitHash // Return the fetched commit hash for further use
}


// Checks whether a branch is up to date with the destination branch by seeing if it is an ancestor of the destination.
// This is in its own method to avoid pipeline failure if the branch needs updating.
def isBranchUpToDate(destinationBranch) {
    return sh (script: "git merge-base --is-ancestor origin/${destinationBranch} @", returnStatus: true)
}

// Attempts to merge the destination branch into the current branch.
// This is in its own method to avoid automatic pipeline failure if there are merge errors. We want to alert the user of the merge errors.
def tryMerge(String destinationBranch) {
    echo "Attempting to merge origin/${destinationBranch}..."
    return sh(script: "git merge origin/${destinationBranch}", returnStatus: true)
}


// Retrieves the full commit hash from Bitbucket Cloud API, since the webhook only gives us the short version.
def getFullCommitHash(String workspace, String shortCommit) {
    def fullHash = sh(script: "python '${workspace}/python/get_bitbucket_commit_hash.py' ${shortCommit}", returnStdout: true).trim()
    if (!fullHash) {
        error "Failed to retrieve the full commit hash for ${shortCommit}."
    }
    return fullHash
}


// Retrieves the latest commit hash of the current local repository.
def getCurrentCommitHash(){
    return sh (script: "git rev-parse HEAD", returnStdout: true).trim() 
}

// Checks if the currentHash from the local repository and the commitHash from the remote repository are equal.
def isEqualCommitHash(currentHash, commitHash){
    return currentHash.equals(commitHash)
}

// Sends a build status to Bitbucket Cloud API.
def sendBuildStatus(workspace, state, commitHash, deployment = false, javascript = false) {
    try {
        def pythonCommand = "python '${workspace}/python/send_bitbucket_build_status.py' '${commitHash}' '${state}'"
        if (deployment) {
            pythonCommand += " -d"
        }
        if (javascript) {
            pythonCommand += " -js -key ${env.SONAR_PROJECT_KEY}"
        }
        echo "Executing build status update: ${pythonCommand}"
        def exitCode = sh(script: pythonCommand, returnStatus: true)
        if (exitCode != 0) {
            echo "Build status update script failed with exit code: ${exitCode}."
        }
    } catch (Exception e) {
        echo "An error occurred while updating the build status: ${e.getMessage()}"
    }
}

def checkIfFileIsLocked(filePath) {
    return bat (script: """2>nul (
            >>\"${filePath}\" (call )
        ) && (exit 0) || (exit 1)""", returnStatus: true)
}

// Parses a Jira ticket number from the branch name.
def parseTicketNumber(branchName) {
    def patternMatches = branchName =~ /[A-Za-z]+-[0-9]+/
    
    if (patternMatches) {
        return patternMatches[0]
    }
}

// Publishes a test result HTML file to the VARLab's remote web server for hosting.
def publishTestResultsHtmlToWebServer(remoteProjectFolderName, ticketNumber, reportDir, reportType, buildNumber = null) {
    echo "Attempting to publish results to web server"
    def destinationDir = buildNumber ? "/var/www/html/${remoteProjectFolderName}/Reports/${ticketNumber}/Build-${buildNumber}/${reportType}-report" : "/var/www/html/${remoteProjectFolderName}/Reports/${ticketNumber}/${reportType}-report"

     sh """ssh vconadmin@dlx-webhost.canadacentral.cloudapp.azure.com \
    \"mkdir -p ${destinationDir} \
    && sudo chown vconadmin:vconadmin ${destinationDir} \
    && sudo chmod 755 /var/www/html/${remoteProjectFolderName} \
    && sudo chmod -R 755 /var/www/html/${remoteProjectFolderName}/Reports \""""

    sh "scp -i C:/Users/ci-catherine/.ssh/vconkey1.pem -rp \"${reportDir}/*\" \
    \"vconadmin@dlx-webhost.canadacentral.cloudapp.azure.com:${destinationDir}\""
}

// Deletes a branch's reports from the web server after it has been merged.
def cleanMergedBranchReportsFromWebServer(remoteProjectFolderName, ticketNumber) {
    sh """ssh vconadmin@dlx-webhost.canadacentral.cloudapp.azure.com \
    \"sudo rm -r -f /var/www/html/${remoteProjectFolderName}/Reports/${ticketNumber}\""""
}

def cleanUpPRBranch(String prBranch) {
    // Find the branch path
    def branchPath = sh(script: "/usr/bin/find ../ -type d -name \"${prBranch}\"", returnStdout: true).trim()

    if (!branchPath.isEmpty()) {
        // Print the path of branch path trying to delete
        echo "Branch Path: ${branchPath}"

        try{
            // Check whether there are open files in the target directory
            def openFiles = bat(script: "handle.exe ${prBranch}", returnStdout: true).trim()
        
            if (!openFiles.isEmpty()) {
                echo "Open files found in the directory: ${branchPath}"
                echo "List of opened files:"
                echo "${openFiles}"

                // Extract unique PIDs from the open files
                // 1. Extract PID list for each line
                // 2. Extract only lines that contain "pid" from the extracted lines
                // 3. Recursively find all elements in the extracted string that contain "pid:" followed by a space " " and then a "number"
                //      >> Exclude the elements which have 'explorer.exe'. It should not be terminated
                // 4. If matching succeeds, returns PID, otherwise null
                def pids = openFiles.split('\n').findAll { it.contains('pid:') && !it.contains('explorer.exe')  && it.contains("${prBranch}")}.collect { line ->
                    def match = line =~ /pid:\s+(\d+)/
                    return match ? match[0][1] : null
                }.unique()

                // Print the PIDs
                echo "List of PIDs of open log files at the \"${prBranch}\": ${pids}"

                // Forcefully terminate the processes
                pids.each { pid -> 
                    if (pid) { 
                        // Check whether the target PID still exists or not
                        // This PowerShell script combines two operations:
                        // 1. Get process information by PID using 'Get-Process'
                        //    >> If no process is associated with the specified PID, it returns nothing because of the "-ErrorAction SilentlyContinue" flag
                        // 2. Extract the PID from the 'Get-Process' result
                        //    >> The output of 'Get-Process' is passed through the pipeline ('|')
                        //    >> The 'Id' property is extracted from the current object ('$_'), which is provided by the 'Get-Process' result
                        // 
                        // Therefore:
                        // - If the process associated with the specified PID exists, this script will return the PID (e.g., "0000")
                        // - If no process is associated with the specified PID, the script will return an empty result
                        echo "Checking whether the target PID still exists or not..."
                        def pidExists = bat(script: 'powershell -Command "Get-Process -Id ${pid} -ErrorAction SilentlyContinue | ForEach-Object { $_.Id }"', returnStdout: true).trim()

                        if (!pidExists.isEmpty()) {
                            // Terminate the process using pid
                            echo "PID ${pid} exists. Proceeding to terminate."
                            bat(script: "taskkill /PID ${pid} /F") 
                            echo "Terminated PID: ${pid}" 
                        } else {
                            echo "PID ${pid} does not exist. Skipping termination."
                        }
                    }
                }
            } 
        }
        catch (Exception e){
            echo "Command failed with error: ${e.message}"
            if (e.message.contains("script returned exit code 1")) {
                // This part will be executed if there is no open file at the target PR directory
                echo "Exit code 1 detected. Likely 'No matching handles found'."
                echo "No open files found in the directory: ${branchPath} Proceeding."
            } else {
                throw e // Unexpected Error
            }
        }
        

        // Clean up the PRJob/{PR_BRANCH} directory
        sh "rm -r -f \"${branchPath}\""
        sh "rm -r -f \"${branchPath}@tmp\""
        
    }
}

return this