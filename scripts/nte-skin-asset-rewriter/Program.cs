using UAssetAPI;
using UAssetAPI.UnrealTypes;
using UAssetAPI.ExportTypes;
using UAssetAPI.Kismet.Bytecode;
using Newtonsoft.Json;
using Newtonsoft.Json.Linq;
var root = Path.GetFullPath(args[0]);
var assetName=args.Length>2?args[2]:"BP_Star";
var original = UAsset.DeserializeJson(File.ReadAllText(Path.Combine(root,"json/HT/Content/MOD/"+assetName+".json")));
var parsed = UAsset.DeserializeJson(File.ReadAllText(Path.Combine(root,"json-parsed/HT/Content/MOD/"+assetName+".json")));
byte[] Serialize(UAsset asset, KismetExpression[] code, out int memorySize) {
 using var buffer=new MemoryStream(); using var writer=new AssetBinaryWriter(buffer,asset);
 memorySize=0; foreach(var expression in code) memorySize+=ExpressionSerializer.WriteExpression(expression,writer);
 return buffer.ToArray();
}
if(args[1]=="measure") {
 var asset=UAsset.DeserializeJson(File.ReadAllText(Path.Combine(root,"edited-functions.json")));
 // Recompute context skip sizes from the actual child bytecode, bottom up.
 foreach(var fn in asset.Exports.OfType<FunctionExport>()) foreach(var top in fn.ScriptBytecode) {
  uint n=0;var nodes=new List<KismetExpression>();top.Visit(asset,ref n,(child,at)=>nodes.Add(child));
  foreach(var child in nodes.AsEnumerable().Reverse()) if(child is UAssetAPI.Kismet.Bytecode.Expressions.EX_Context ctx) {
   uint size=0;ctx.ContextExpression.Visit(asset,ref size,(_,__)=>{});ctx.Offset=size;
  }
 }
 File.WriteAllText(Path.Combine(root,"edited-functions.json"),asset.SerializeJson());
 var result=new Dictionary<int,object>();
 foreach(var fn in asset.Exports.OfType<FunctionExport>()) {
  var sizes=new List<uint>();var addresses=new List<uint>();uint pos=0;
  foreach(var x in fn.ScriptBytecode){addresses.Add(pos);uint start=pos;x.Visit(asset,ref pos,(_,__)=>{});sizes.Add(pos-start);}
  result[asset.Exports.IndexOf(fn)]=new {sizes,addresses,total=pos};
 }
 File.WriteAllText(Path.Combine(root,"universal-measure.json"),JsonConvert.SerializeObject(result,Formatting.Indented));return;
}
if(args[1]=="baseline") {
 var output=Path.Combine(root,"baseline/BP_Star.uasset");Directory.CreateDirectory(Path.GetDirectoryName(output)!);
 original.Write(output);
 for(int i=0;i<parsed.Exports.Count;i++) if(parsed.Exports[i] is FunctionExport fn) {
  var script=Serialize(parsed,fn.ScriptBytecode,out var memorySize);
  var raw=((RawExport)original.Exports[i]).Data;
  int found=-1; for(int k=8;k<=raw.Length-script.Length;k++) if(raw.AsSpan(k,script.Length).SequenceEqual(script)) {
   if(found!=-1) throw new Exception("ambiguous script location");found=k;
  }
  if(found<8 || BitConverter.ToInt32(raw,found-8)!=memorySize || BitConverter.ToInt32(raw,found-4)!=script.Length) throw new Exception("script roundtrip mismatch: "+fn.ObjectName);
  Console.WriteLine($"{i} {fn.ObjectName} prefix={found} storage={script.Length} memory={memorySize}");
 }
 return;
}
if(args[1]=="validate") {
 var asset=UAsset.DeserializeJson(File.ReadAllText(Path.Combine(root,"reparsed/HT/Content/MOD/"+assetName+".json")));
 foreach(var fn in asset.Exports.OfType<FunctionExport>()) {
  uint pos=0;var boundaries=new HashSet<uint>();var all=new List<KismetExpression>();
  foreach(var x in fn.ScriptBytecode) {boundaries.Add(pos);x.Visit(asset,ref pos,(child,at)=>all.Add(child));}
  if(pos!=fn.ScriptBytecodeSize)throw new Exception("VM memory size differs: "+fn.ObjectName);
  foreach(var x in all) {
   uint? target=x switch {UAssetAPI.Kismet.Bytecode.Expressions.EX_Jump a=>a.CodeOffset,UAssetAPI.Kismet.Bytecode.Expressions.EX_JumpIfNot a=>a.CodeOffset,UAssetAPI.Kismet.Bytecode.Expressions.EX_PushExecutionFlow a=>a.PushingAddress,_=>null};
   if(target.HasValue && !boundaries.Contains(target.Value))throw new Exception("invalid jump in "+fn.ObjectName);
  }
  Console.WriteLine($"valid {fn.ObjectName} expressions={fn.ScriptBytecode.Length} VM={pos}");
 }
 var mainIndex=assetName=="BP_Star"?2:6;var main=(FunctionExport)asset.Exports[mainIndex];uint mo=0;var mainBoundaries=new HashSet<uint>();foreach(var x in main.ScriptBytecode){mainBoundaries.Add(mo);x.Visit(asset,ref mo,(_,__)=>{});}
 foreach(var fn in asset.Exports.OfType<FunctionExport>())foreach(var x in fn.ScriptBytecode) {
  uint n=0;x.Visit(asset,ref n,(child,at)=> {
   if(child is UAssetAPI.Kismet.Bytecode.Expressions.EX_LocalFinalFunction c && c.StackNode.Index==mainIndex+1) {
    var entry=(UAssetAPI.Kismet.Bytecode.Expressions.EX_IntConst)c.Parameters[0];if(!mainBoundaries.Contains((uint)entry.Value))throw new Exception("invalid ubergraph entry");
   }
  });
 }
 return;
}
var edits=UAsset.DeserializeJson(File.ReadAllText(Path.Combine(root,"edited-functions"+(assetName=="BP_Star"?"":"-ui")+".json")));
// Preserve original opaque exports, but adopt appended names/imports from the edited AST.
var rawTree=JObject.Parse(original.SerializeJson());var editTree=JObject.Parse(edits.SerializeJson());
rawTree["NameMap"]=editTree["NameMap"]!.DeepClone();rawTree["Imports"]=editTree["Imports"]!.DeepClone();
original=UAsset.DeserializeJson(rawTree.ToString());
var receipt=new List<object>();
for(int i=0;i<parsed.Exports.Count;i++) if(parsed.Exports[i] is FunctionExport fn) {
 var oldScript=Serialize(parsed,fn.ScriptBytecode,out var oldMemory);
 var raw=((RawExport)original.Exports[i]).Data;
 int offset=-1;for(int k=8;k<=raw.Length-oldScript.Length;k++) if(raw.AsSpan(k,oldScript.Length).SequenceEqual(oldScript)){if(offset!=-1)throw new Exception("ambiguous");offset=k;}
 if(offset<8 || BitConverter.ToInt32(raw,offset-8)!=oldMemory || BitConverter.ToInt32(raw,offset-4)!=oldScript.Length)throw new Exception("original not lossless");
 var newFn=(FunctionExport)edits.Exports[i]; var replacement=Serialize(edits,newFn.ScriptBytecode,out var newMemory);
 using var buffer=new MemoryStream();buffer.Write(raw,0,offset-8);buffer.Write(BitConverter.GetBytes(newMemory));buffer.Write(BitConverter.GetBytes(replacement.Length));buffer.Write(replacement);buffer.Write(raw,offset+oldScript.Length,raw.Length-offset-oldScript.Length);
 ((RawExport)original.Exports[i]).Data=buffer.ToArray();
 receipt.Add(new {export=i,name=fn.ObjectName.ToString(),oldStorage=oldScript.Length,newStorage=replacement.Length});
}
// The validated input binding records were reduced to the two skin keys.
if(assetName=="BP_Star") ((RawExport)original.Exports[32]).Data=Convert.FromBase64String(File.ReadAllText(Path.Combine(root,"skin-bindings.base64")));
var path=Path.Combine(root,"edited/HT/Content/MOD/"+assetName+".uasset");Directory.CreateDirectory(Path.GetDirectoryName(path)!);original.Write(path);
File.WriteAllText(Path.Combine(root,assetName+"-function-rewrite-receipt.json"),JsonConvert.SerializeObject(receipt,Formatting.Indented));
Console.WriteLine(path);
