# 鸣潮本地换肤模块可行性研究

研究日期：2026-10-14。目标客户端：
`E:\Games\Wuthering Waves\Wuthering Waves Game\Client`。
本次只读取游戏二进制、资源包索引和文件版本；没有加载 DLL、附加游戏进程、
改动客户端或修改账号数据。证据保存在本地忽略目录 `tools/wuwa-skin-analysis`。

## 结论

有实现类似本地外观切换模块的技术基础，但尚未取得当前版本的角色服装业务实现，
因此不能声称已经确认一个可用的完整调用链。异环的 HTPlayerCharacter 和
FashionDyeData 不能直接用于鸣潮。

合理的候选路线是：本地当前操控角色 → 游戏逻辑中的服装配置/模型资源 →
该角色的外观构建及加载完成回调。原生 ASI/DLL 可以充当按键和调用入口，
但服装识别及刷新应追踪游戏逻辑，而不能把注入成功当作换肤成功。

## 当前客户端证据

| 观察 | 证据 | 可支持的结论 |
| --- | --- | --- |
| UE4.26 版本字符串 | 主 EXE 含 ++UE4+Release-4.26-CL-180055842 | 此构建含 UE4.26 分支标记；不证明所有格式未定制 |
| C# 游戏加载入口 | CSharpScript.Game、Aki.Game.dll、UnrealEngine.dll | 当前二进制包含托管游戏逻辑加载引用 |
| C# 原生桥 | UCSharpBlueprintFunctionLibrary 的 CSharpDoMain、CallCSharpFunction、LoadDeferredRuntimeAssemblies 等绑定名称 | 存在原生与托管代码之间的入口名称；签名及运行调用尚未确认 |
| 运行时文件 | coreclr.dll 的 ProductVersion 为 9.0.6 | 本地带有 .NET 运行时文件；不证明所有游戏逻辑已迁移至 C# |
| 模型替换底层能力 | USkinnedMeshComponent::__SetSkeletalMesh_Internal | 存在通用骨骼模型设置绑定；不等同于完整服装刷新接口 |
| 游戏自有角色材质控制 | UKuroCharacterMaterialControllerCache 绑定集合 | 有角色材质参数控制层；不证明它控制整套服装资源 |
| 现有加载器 | d3d11.dll 的产品及版本为 Ultimate ASI Loader 9.7.4 | 可作为后续模块加载的候选基础；本次未验证新插件加载 |

`d3d11.dll` 是符号链接，实际指向
`E:\wwdlss5\xxmi+reshade680+sm\d3d11.dll`。分析时读取的是链接后的真实文件，
没有替换它或调整现有 WWMI/图形插件加载链。
主 EXE 和 ShippingBase DLL 的 PE CLR directory 均为零，因此它们不是可直接用
托管反编译器打开的 Aki.Game 程序集；不能混淆 native host 与 managed game code。
还有 TypeScript 动画通知资源路径，故没有假设当前版本的所有脚本都是 C#。

## 已排除的错误入口

`PreviewSkin`、`SetSkin` 的邻近类名指向 SpinePlugin.SpineSkeletonComponent，
这是二维 Spine 骨骼皮肤功能，不能用于三维角色服装。
`SkinDyeColor` 位于 NpcSetupData、Skel_Hair/Body 等字段附近，不能当作玩家服装 setter。
`ChangeRole` 位于 SQteTag 相关名称附近，不能单凭名称解释为换皮肤。
通用 Skinning、SkinCache 和着色模型 PreintegratedSkin 也不属于服装管理。

## 资源读取结果与尚未完成的部分

Content/Paks 下 55 个 pak 的末尾信息可读取，版本字段为 12；其中 54 个设置了
索引加密标志。不能将这些文件直接当成异环的 UE5 IoStore 容器来处理。
未在展开的客户端目录找到 Aki.Game.dll 和 UnrealEngine.dll 的独立文件；
它们可能在封装资源或延迟加载数据中，但本次没有确认具体归档位置。

pakchunk43 的索引未加密：已解析其主索引和完整目录索引，准确读取 348,420 条
文件记录。挂载路径为 Aki/Config/UniverseEditorConfig，内容包括 Levels、
EntityOwners、Templates、ActorRefConfig、Quests 等关卡实体配置；并非已找到
角色服装业务代码。读取 FString 时同时处理 UTF-8 与 UTF-16，目录字节完整消耗。

[CUE4Parse 的 PakFileReader 源码](https://github.com/FabianFG/CUE4Parse/blob/master/CUE4Parse/UE4/Pak/PakFileReader.cs)
专门处理 GAME_WutheringWaves 的自定义 pak 版本及部分加密提取。
因此下一步应该使用当前鸣潮格式的资源读取链取得程序集/脚本和服装配置，
而不是复用 retoc 的异环流水线或根据旧版本源码硬编码偏移。

还需要实际确认：当前角色实体与角色编号、服装编号与资源的对应表、模型/材质/
布料/附件的共同刷新流程、异步加载后的绑定，以及角色切换时是否会重写外观。
也尚未核实服装选择中哪些检查只影响本地展示、哪些由服务端决定。
本地外观替换不能等同于获得账号服装权益。

当前不生成或安装一个只有注入外壳、却缺少有效角色刷新调用的 DLL。
可行性判断是有依据的候选方案，尚无鸣潮游戏内验证结果。
