# 当前角色皮肤切换（2026-10-14）

该模块只保留 `-` 服装切换、`=` 染色切换。输入绑定仅两条，其余输入事件及 Tick
均为空函数；没有恢复瞬移、飞行、NPC 操作或位置保存。

用户验证换装效果后要求移除顶部提示：BeginPlay 在启用输入后直接返回，不再创建
快捷键提示 Widget，TXT9 提示更新函数也改为空函数。两个操作按键仍保留。

角色识别由对象显示名称拆分，改成游戏反射接口：
`GetPlayerController(0) → HTPlayerController.GetPlayerCharacter() →
HTPlayerCharacter.GetCurrentDisplayCharacterID()`。
本地游戏反射元数据确认了上述函数的所属类和参数类型。每次按键都核对当前显示角色
和缓存第一行的 PlayerID；不匹配则重置服装/染色索引、重建角色行列表。新列表为空
时返回，避免读空数组。新列表有效时先刷新初始服装及染色上限，再执行此次操作。

外观修改继续使用原包的本地角色属性和刷新回调。先复制完整旧 FashionDyeData 到
已有局部结构体，写入新 FashionID/DyeID，更新 CurrentDisplayFashionID，然后调用
OnRep_FashionDyeData(旧数据)。材质接口 k2_ApplyFashionDyeMaterials 的第三个参数
改为当前 InCharacterID，第四个 appearance mask 保留原包的零值。
原包将更新后的数据作为 OldFashionDyeData 传入，本版本修正了这个语义错误。
Unreal 对这类回调参数的旧值语义见
[官方复制属性文档](https://dev.epicgames.com/documentation/unreal-engine/replicate-actor-properties-in-unreal-engine)。

SetFashionDyeData 等原生 setter 的签名已确认，但受保护的原生执行代码仍未完成解析；
无法仅凭函数名字证明它是否会重建模型，因此没有用它替换已有刷新链。
这属于实现选择，不代表现有链已完成全角色运行验证。

`scripts/build_nte_all_roles.py` 修改暂存 AST，再调用 UAssetAPI 辅助工具测量并重定位
所有跳转及 ubergraph 入口。`scripts/nte-skin-asset-rewriter/Program.cs` 是对应工具源码，
它保留原始函数的属性前缀/尾部及所有不透明导出，只替换脚本字节码；无映射信息的
类属性不重新解释或序列化。构建所需本地解码资产、游戏反射表及第三方依赖不提交。
本地现有工具路径为 tools/skin-unlock-analysis/SkinOnlyTool；可将公开辅助工具的
编译结果放到该路径，或调整生成脚本 TOOL 常量。

成品重新经 retoc 转回 legacy，解码所有函数并核对与预期 AST 相同（只规范化空的
ArrayInnerProp）；所有其它包的导出内容保持原样，函数跳转/入口边界合法。
`scripts/verify_nte_all_roles.py` 使用真实服装表及成品按键字节码进行 1,404 组
缓存/切换角色/未知角色模拟，原生调用由模拟函数替代。
表内 101 行、25 个角色编号证明了数据覆盖范围，不能证明所有编号都是当前可玩角色，
也不能证明角色模型实际加载成功。游戏内验证由用户执行。

安装只替换外部 SkinSwitch 的 pak/utoc/ucas 和 skin-switch.json 清单，先移除自有
IMM-SkinSwitch 链接再更新，最后恢复此前启用状态。未替换 IMM、启动器、UAL、
原生加载器、bypass 或反虚化插件，也未修改 IMM 的配置。
