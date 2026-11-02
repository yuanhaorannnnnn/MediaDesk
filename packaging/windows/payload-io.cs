using System;
using System.Collections.Generic;
using System.Diagnostics;
using System.IO;
using System.Security.Cryptography;

// Batches filesystem work inside .NET instead of invoking thousands of PowerShell cmdlets.
public static class MediaDeskPayloadIO {
    static void CheckPath(string path, string root, HashSet<string> directories) {
        string cursor=path;
        bool first=true;
        while(cursor.Length>=root.Length) {
            if(!first && directories.Contains(cursor)) break;
            try {
                FileAttributes attrs=File.GetAttributes(cursor);
                if((attrs & FileAttributes.ReparsePoint)!=0) throw new IOException("Refusing reparse point: "+cursor);
                if((attrs & FileAttributes.Directory)!=0) directories.Add(cursor);
            } catch(FileNotFoundException) {} catch(DirectoryNotFoundException) {}
            if(String.Equals(cursor,root,StringComparison.OrdinalIgnoreCase)) break;
            cursor=Path.GetDirectoryName(cursor);
            if(cursor==null) break;
            first=false;
        }
    }
    static string Local(string root,string relative) {
        string path=Path.GetFullPath(Path.Combine(root,relative));
        if(!path.StartsWith(root+Path.DirectorySeparatorChar,StringComparison.OrdinalIgnoreCase)) throw new IOException("Payload path escaped root");
        return path;
    }
    static string Hash(string path,SHA256 sha) {
        using(FileStream stream=new FileStream(path,FileMode.Open,FileAccess.Read,FileShare.Read)) {
            return BitConverter.ToString(sha.ComputeHash(stream)).Replace("-","");
        }
    }
    public static void Verify(string root,string[] paths,string[] hashes) {
        if(paths.Length!=hashes.Length) throw new IOException("Invalid payload vectors");
        int verified=0;
        // Bound concurrent reads to avoid serial per-file scan latency without skipping hashes.
        System.Threading.Tasks.Parallel.For(0,Math.Min(16,paths.Length),worker => {
            HashSet<string> dirs=new HashSet<string>(StringComparer.OrdinalIgnoreCase);
            using(SHA256 sha=SHA256.Create()) {
                for(int i=worker;i<paths.Length;i+=Math.Min(16,paths.Length)) {
                    string source=Local(root,paths[i]);CheckPath(source,root,dirs);
                    if(!String.Equals(Hash(source,sha),hashes[i],StringComparison.OrdinalIgnoreCase)) throw new IOException("Runtime checksum mismatch: "+paths[i]);
                    int count=System.Threading.Interlocked.Increment(ref verified);
                    if(count%2000==0) Console.WriteLine("Verified runtime files: "+count+"/"+paths.Length);
                }
            }
        });
    }
    public static int[] CopyResume(string sourceRoot,string root,string[] paths,string[] hashes) {
        int copied=0,reused=0;
        HashSet<string> dirs=new HashSet<string>(StringComparer.OrdinalIgnoreCase);
        using(SHA256 sha=SHA256.Create()) {
            for(int i=0;i<paths.Length;i++) {
                string target=Local(root,paths[i]);CheckPath(target,root,dirs);
                if(File.Exists(target)) {
                    if(!String.Equals(Hash(target,sha),hashes[i],StringComparison.OrdinalIgnoreCase)) throw new IOException("Changed staged file retained: "+paths[i]);
                    reused++;continue;
                }
                Directory.CreateDirectory(Path.GetDirectoryName(target));
                string partial=target+".copying";CheckPath(partial,root,dirs);
                File.Copy(Local(sourceRoot,paths[i]),partial,true);
                if(!String.Equals(Hash(partial,sha),hashes[i],StringComparison.OrdinalIgnoreCase)) throw new IOException("Copied runtime checksum mismatch: "+paths[i]);
                File.Move(partial,target);copied++;
                if((i+1)%2000==0) Console.WriteLine("Copied runtime files: "+(i+1)+"/"+paths.Length);
            }
        }
        return new int[]{copied,reused};
    }
    public static void ValidatePaths(string root,string[] paths) {
        HashSet<string> dirs=new HashSet<string>(StringComparer.OrdinalIgnoreCase);
        foreach(string relative in paths) CheckPath(Local(root,relative),root,dirs);
    }
    public static string[] DeleteOwned(string root,string[] paths,string[] hashes) {
        ValidatePaths(root,paths);
        List<string> kept=new List<string>();
        HashSet<string> dirs=new HashSet<string>(StringComparer.OrdinalIgnoreCase);
        using(SHA256 sha=SHA256.Create()) {
            for(int i=0;i<paths.Length;i++) {
                string path=Local(root,paths[i]);CheckPath(path,root,dirs);
                if(!File.Exists(path)) continue;
                if(!String.Equals(Hash(path,sha),hashes[i],StringComparison.OrdinalIgnoreCase)) {kept.Add(path);continue;}
                FileAttributes attrs=File.GetAttributes(path);
                if((attrs&FileAttributes.ReadOnly)!=0) File.SetAttributes(path,attrs&~FileAttributes.ReadOnly);
                File.Delete(path);
            }
        }
        return kept.ToArray();
    }
    public static void RemoveEmptyDirectories(string root) {
        Queue<string> pending=new Queue<string>();List<string> dirs=new List<string>();pending.Enqueue(root);
        while(pending.Count>0) {
            foreach(string dir in Directory.GetDirectories(pending.Dequeue())) {
                if((File.GetAttributes(dir)&FileAttributes.ReparsePoint)!=0) continue;
                dirs.Add(dir);pending.Enqueue(dir);
            }
        }
        dirs.Sort(delegate(string left,string right) {return right.Length.CompareTo(left.Length);});
        foreach(string dir in dirs) {
            using(IEnumerator<string> entries=Directory.EnumerateFileSystemEntries(dir).GetEnumerator()) {
                if(entries.MoveNext()) continue;
            }
            Directory.Delete(dir);
        }
    }
    public static void ExtractArchive(string archive,string root,string[] paths,long[] sizes,string expectedArchiveHash) {
        Dictionary<string,int> expected=new Dictionary<string,int>(StringComparer.OrdinalIgnoreCase);
        for(int i=0;i<paths.Length;i++) expected.Add(paths[i],i);
        Stopwatch timer=Stopwatch.StartNew();
        // Keep a read-only handle open through native extraction, preventing archive replacement/writes.
        using(FileStream source=new FileStream(archive,FileMode.Open,FileAccess.Read,FileShare.Read)) {
            using(SHA256 sha=SHA256.Create()) {
                string digest=BitConverter.ToString(sha.ComputeHash(source)).Replace("-","");
                if(!String.Equals(digest,expectedArchiveHash,StringComparison.OrdinalIgnoreCase)) throw new IOException("Runtime archive checksum mismatch");
            }
            Console.WriteLine("Archive checksum seconds: "+timer.Elapsed.TotalSeconds.ToString("F2"));
            source.Position=0;
            HashSet<string> seen=new HashSet<string>(StringComparer.OrdinalIgnoreCase);
            using(System.IO.Compression.ZipArchive zip=new System.IO.Compression.ZipArchive(source,System.IO.Compression.ZipArchiveMode.Read,true)) {
                foreach(System.IO.Compression.ZipArchiveEntry entry in zip.Entries) {
                    string relative=entry.FullName.Replace('/','\\');int index;
                    int mode=(entry.ExternalAttributes>>16)&0xF000;
                    if((mode!=0 && mode!=0x8000) || (entry.ExternalAttributes&0x400)!=0 || entry.Name.Length==0) throw new IOException("Unsupported archive file type");
                    if(!expected.TryGetValue(relative,out index) || !seen.Add(relative) || sizes[index]<0 || entry.Length!=sizes[index]) throw new IOException("Unknown, duplicate or size-mismatched archive entry: "+relative);
                    Local(root,relative);
                }
            }
            if(seen.Count!=paths.Length) throw new IOException("Archive is missing payload files");
            string tar=Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.System),"tar.exe");
            if(!File.Exists(tar)) throw new IOException("This Windows installation lacks its built-in archive extractor");
            ProcessStartInfo info=new ProcessStartInfo(tar,"-xf \""+archive+"\" -C \""+root+"\"");
            info.UseShellExecute=false;info.CreateNoWindow=true;timer.Restart();
            Console.WriteLine("Runtime stage: extracting archive; completion is reported only after extraction exits successfully");
            using(Process child=Process.Start(info)) {child.WaitForExit();if(child.ExitCode!=0) throw new IOException("Native archive extraction failed: "+child.ExitCode);}
            Console.WriteLine("Native archive extraction seconds: "+timer.Elapsed.TotalSeconds.ToString("F2"));
        }
        // Check extracted path types without reopening every file for a content hash.
        timer.Restart();ValidatePaths(root,paths);
        Console.WriteLine("Extracted path safety check seconds: "+timer.Elapsed.TotalSeconds.ToString("F2"));
    }
}
