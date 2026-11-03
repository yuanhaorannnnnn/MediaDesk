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
        HashSet<string> dirs=new HashSet<string>(StringComparer.OrdinalIgnoreCase);
        using(SHA256 sha=SHA256.Create()) {
            for(int i=0;i<paths.Length;i++) {
                string source=Local(root,paths[i]);CheckPath(source,root,dirs);
                if(!String.Equals(Hash(source,sha),hashes[i],StringComparison.OrdinalIgnoreCase)) throw new IOException("Runtime checksum mismatch: "+paths[i]);
                if((i+1)%2000==0) Console.WriteLine("Verified runtime files: "+(i+1)+"/"+paths.Length);
            }
        }
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
    public static void ExtractArchive(string archive,string root,string[] paths,string[] hashes,long[] sizes,string expectedArchiveHash) {
        Dictionary<string,int> expected=new Dictionary<string,int>(StringComparer.OrdinalIgnoreCase);
        for(int i=0;i<paths.Length;i++) expected.Add(paths[i],i);
        Stopwatch timer=Stopwatch.StartNew();
        using(FileStream source=new FileStream(archive,FileMode.Open,FileAccess.Read,FileShare.Read)) {
            using(SHA256 sha=SHA256.Create()) {
                string digest=BitConverter.ToString(sha.ComputeHash(source)).Replace("-","");
                if(!String.Equals(digest,expectedArchiveHash,StringComparison.OrdinalIgnoreCase)) throw new IOException("Runtime archive checksum mismatch");
            }
            Console.WriteLine("Locked archive checksum seconds: "+timer.Elapsed.TotalSeconds.ToString("F2"));
            source.Position=0;
            HashSet<string> seen=new HashSet<string>(StringComparer.OrdinalIgnoreCase);
            using(System.IO.Compression.ZipArchive zip=new System.IO.Compression.ZipArchive(source,System.IO.Compression.ZipArchiveMode.Read,true)) {
                // Check every entry before creating any payload file, including type, size and path.
                foreach(System.IO.Compression.ZipArchiveEntry entry in zip.Entries) {
                    string relative=entry.FullName.Replace('/','\\');int index;
                    int mode=(entry.ExternalAttributes>>16)&0xF000;
                    if((mode!=0 && mode!=0x8000) || (entry.ExternalAttributes&0x400)!=0 || entry.Name.Length==0) throw new IOException("Unsupported archive file type");
                    if(!expected.TryGetValue(relative,out index) || !seen.Add(relative) || sizes[index]<0 || entry.Length!=sizes[index]) throw new IOException("Unknown, duplicate or size-mismatched archive entry: "+relative);
                    Local(root,relative);
                }
                if(seen.Count!=paths.Length) throw new IOException("Archive is missing payload files");
                byte[] buffer=new byte[131072];HashSet<string> dirs=new HashSet<string>(StringComparer.OrdinalIgnoreCase);
                timer.Restart();Stopwatch hashTimer=new Stopwatch();int completed=0;
                using(SHA256 sha=SHA256.Create()) {
                    foreach(System.IO.Compression.ZipArchiveEntry entry in zip.Entries) {
                        string relative=entry.FullName.Replace('/','\\');int index=expected[relative];
                        string target=Local(root,relative);CheckPath(target,root,dirs);Directory.CreateDirectory(Path.GetDirectoryName(target));
                        string partial=target+".copying";CheckPath(partial,root,dirs);long written=0;
                        using(Stream input=entry.Open()) using(FileStream output=new FileStream(partial,FileMode.CreateNew,FileAccess.Write,FileShare.None)) {
                            int count;
                            while((count=input.Read(buffer,0,buffer.Length))>0) {
                                written+=count;if(written>sizes[index]) throw new IOException("Archive entry exceeded declared size");
                                output.Write(buffer,0,count);
                            }
                        }
                        if(written!=sizes[index]) throw new IOException("Archive entry was truncated");
                        // Read back each completed file while it is still local in the filesystem cache.
                        hashTimer.Start();string digest=Hash(partial,sha);hashTimer.Stop();
                        if(!String.Equals(digest,hashes[index],StringComparison.OrdinalIgnoreCase)) throw new IOException("Extracted runtime checksum mismatch: "+relative);
                        File.Move(partial,target);completed++;
                        if(completed%2000==0) Console.WriteLine("Extracted and verified files: "+completed+"/"+paths.Length);
                    }
                }
                Console.WriteLine("Entry extraction and verification seconds: "+timer.Elapsed.TotalSeconds.ToString("F2"));
                Console.WriteLine("Immediate target hashing seconds: "+hashTimer.Elapsed.TotalSeconds.ToString("F2"));
            }
        }
    }
}
