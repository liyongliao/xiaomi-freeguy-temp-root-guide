# SELinux 研究记录：2026-10-24

## 已确认结果

设备和完整构建指纹见 [README](../README.md)。短命令实际运行于 `uid=0 / u:r:misysdiagnose:s0`，全局 SELinux 为 Enforcing。旧测试对 `boot_a` 前 8 字节的只读访问已经返回 Permission denied；本轮可读性探针仍失败。没有取得完整临时 Root，没有生成原始分区镜像。

本轮另从诊断域只读导出 `/vendor/bin/misysdiagnose`，待全部日志到齐后重建为 ELF，并与设备计算的摘要核对。中途 19,266 字节的结果未通过校验，已拒绝作为完整副本；最终是 26,656 字节：

```text
62b8b6ae2cd2d803fa788592bbb7814a9c87c38adcbdea4ae14e77ae4060a610
```

REA 文件检查确认 `elf32-littlearm`。导入符号有 `system`、`popen`；这只证明依赖关系，不代替完整函数反编译或证明存在新的利用路径。当前分析环境没有可用的 REA 深度反编译引擎；使用已安装 objdump 完成文件格式及反汇编检查，没有执行该 ELF。原厂二进制不公开分发。

## 策略审计方法与边界

输入为本机 `plat_sepolicy.cil`、`system_ext_sepolicy.cil`、`product_sepolicy.cil`、`vendor_sepolicy.cil`，以及 system/system_ext/product 的 `mapping/34.0.cil`。展开同名属性的多处定义、嵌套属性与布尔集合表达式。

- 40,787 条顶层表达式，2,502 个具体类型。
- 属性闭包未解析符号为 0。
- `misysdiagnose` 匹配 678 条 allow / allowx / 类型转换表达式。
- 输入没有条件块、宏或继承块。

这不是对运行中策略的形式化等价证明：未反序列化二进制策略以逐位比较，未求值全部 MLS/约束、DAC 和内核访问钩子。静态未见允许规则与已观察到的运行时拒绝相互支持，但不能据此排除厂商组件的所有漏洞。

原机已保存的 `/vendor/etc/selinux/precompiled_sepolicy` 摘要：

```text
05b88ce4eb2763e63c7049fbfcf8ca6b8c5b08a58a4e6fef9ff6c82677061a06
```

## 逐项结论

| 候选操作 | 已分析范围内的结论 |
|---|---|
| 关闭 enforcing / 加载策略 | 未见 `security` 类允许规则；selinuxfs 文件权限不足 |
| 读取启动分区 | 未见 `blk_file` 权限，且无 `block_device:dir search` |
| 任意 setcon / runcon | 未见 dyntransition、setcurrent、setexec |
| 注入其他进程 | 未见 process ptrace；部分 proc 文件 read/open 不足以赋予进程内存访问权限 |
| 挂载、重新挂载、重标记 | 未见对应 filesystem mount/remount/relabel 或文件 relabel 权限 |
| 设置属性并启动其他服务 | 未见 property_service set；property socket 的部分访问许可不代表 ctl.start 可用 |
| 执行 shell、toolbox | 通常为 execute_no_trans，不改变当前域 |
| 标准 helper 域转换 | 有 crash_dump、netutils_wrapper；都没有直接的块设备读或策略加载权限 |
| 厂商设备节点、Binder 方法 | 存在部分访问规则，但没有证明任意内存访问或可控高权限代码执行 |

关键原机规则位置：vendor:10791（诊断 ELF 读取）、10821–10826（部分数据目录）、10853/10903（部分 capabilities）、10975（图形设备访问）；plat:20513/20518（crash_dump 转换）、23759/23764（netutils_wrapper 转换）。行号只对应本轮已哈希保存的输入文件，不是其他系统版本的稳定位置。

特别注意：`crash_dump` 的某些 ptrace 权限不代表可以把任意程序放进该域。需要另外证明真实可控接口或代码执行漏洞；本轮没有这样的证据，也没有对系统进程进行注入。

## 原机内核配置

通过普通 ADB 只读取得 `/proc/config.gz` 后解压：

```text
CONFIG_ARM64=y
CONFIG_COMPAT=y
# CONFIG_USER_NS is not set
# CONFIG_DEVMEM is not set
# CONFIG_CRYPTO_USER_API_HASH is not set
# CONFIG_CRYPTO_USER_API_SKCIPHER is not set
# CONFIG_CRYPTO_USER_API_RNG is not set
# CONFIG_CRYPTO_USER_API_AEAD is not set
CONFIG_SECURITY_SELINUX=y
CONFIG_SECURITY_SELINUX_DEVELOP=y
# CONFIG_SECURITY_SELINUX_BOOTPARAM is not set
# CONFIG_SECURITY_SELINUX_DISABLE is not set
```

因此不能直接迁移依赖相应命名空间、`/dev/mem` 或用户态加密接口的方案。`CONFIG_SECURITY_SELINUX_DEVELOP=y` 也不表示诊断 UID 0 获准切换 enforcing。

## 仍未解决

设备专用驱动、厂商 Binder 服务、标准 helper 的实现缺陷未被穷尽分析。原始启动镜像不可读，因此也没有完成内核二进制和厂商补丁的逐项核对。没有找到经本机验证、符合“不刷机、不改持久配置、不清数据”范围的完整临时 Root 路径。

此前提供的另一机型 root bundle 面向 mulan / Android 9，依赖已经具备高权限的 Recovery，并会修改策略和启动持久化配置。它不是此设备受限域的临时逃逸方案，没有在本机执行。也没有通过改型号或去掉哈希检查强行套用。

后续仅在有可核验的本机适配证据时继续验证；任何“成功”需同时证明可用的权限边界，并优先完成原始分区备份。
