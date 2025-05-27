using UnityEditor;
using System.Linq;
using UnityEditor.Build.Reporting;

public class Builder
{
    static string[] GetEnabledScenes()
    {
        return (
            from scene in EditorBuildSettings.scenes
            where scene.enabled
            where !string.IsNullOrEmpty(scene.path)
            select scene.path
        ).ToArray();
    }

    static void BuildWebGL()
    {
        // Check if running in CI environment
        if (System.Environment.GetEnvironmentVariable("CI_PIPELINE") == "true")
        {
            // Setting the WebAssembly optimization level to 0 (-O0) to avoid extensive optimizations.
            // This ensures that wasm-opt.exe is not executed, thereby minimizing the CPU usage during the WebGL build process.
            PlayerSettings.WebGL.emscriptenArgs = "-O0 -s";
        }
        BuildReport report = BuildPipeline.BuildPlayer(GetEnabledScenes(), "./Builds/", BuildTarget.WebGL, BuildOptions.None);

        if (report.summary.result == BuildResult.Succeeded) 
        { 
            EditorApplication.Exit(0); 
        }
        else 
        {
            EditorApplication.Exit(1);
        }
    }
}