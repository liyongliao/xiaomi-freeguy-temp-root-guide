# 小米 S85 Mini LED：受限临时 Root 实测记录

这份教程记录在 **freeguy / OS3.0.106.0.UFTMATV** 上，通过原厂 `TvService` 诊断入口执行短时 UID 0 命令的方法。2026-10-23 首次验证，2026-10-24 再次验证并补充 SELinux 属性闭包与内核配置分析。

**当前结果：UID 0 已验证，完整临时 Root 未取得，原始分区备份未完成。** 进程仍在 `u:r:misysdiagnose:s0` 域，SELinux 仍为 Enforcing。这里没有 `su`、root adbd、Magisk、解锁或刷机方案；不要据此覆盖启动分区。

本项目用于机主通过已授权 ADB 管理自己的设备。只发布自编验证脚本、必要的诊断命令和脱敏结论，不分发厂商 APK、诊断 ELF、固件、设备密钥或原始日志。

## 1. 已验证的设备范围

| 项目 | 实测值 |
|---|---|
| 零售名称 | 小米电视 S85 Mini LED，85 英寸 |
| Android 型号 / 代号 | MiTV-MFTR0 / freeguy |
| 主板 / 平台 | DL8C_02 / mt5879（MT9653） |
| 固件 | OS3.0.106.0.UFTMATV |
| Android / SDK | 14 / 34 |
| 用户空间 ABI | armeabi-v7a,armeabi |
| 内核 | 5.4.190-g97bd248eea35-dirty，构建于 2026-02-06 |
| 内核架构 | ARM64，启用 COMPAT 兼容 32 位用户空间 |
| 安全补丁字符串 | 2025-07-05 |
| SELinux / Verified Boot / 槽位 | Enforcing / green / _a |

完整构建指纹：

```text
xiaomi/freeguy/freeguy:14/UQ1A.240105.004.A1/OS3.0.106.0.UFTMATV:user/release-keys
```

`MiTV-MFTR0` 不是唯一零售型号。同型号名、同芯片、同尺寸都不能代替固件指纹匹配。本项目没有验证其他版本、海外 Google TV 固件或降级方案。

## 2. 连接与版本核对

电脑安装 Android Platform Tools 和 Python 3。电视开启 ADB 调试，在电视上确认这台电脑的调试授权。使用实际地址替换 `TV_IP`；每条命令都明确指定目标，避免操作另一台 Android 设备。

```sh
adb connect TV_IP:5555
adb -s TV_IP:5555 get-state
adb -s TV_IP:5555 shell getprop ro.product.device
adb -s TV_IP:5555 shell getprop ro.build.fingerprint
adb -s TV_IP:5555 shell getenforce
adb -s TV_IP:5555 shell id
```

普通 ADB shell 是 `uid=2000(shell)`，并非 Root。以下方法不需要电视访问外网，也不会修改网络设置。

## 3. 使用验证脚本

先运行预检查。脚本只接受上表中已验证的设备、SDK、ABI 和完整指纹，不会自动适配其他固件：

```sh
python3 scripts/verify_tv.py --serial TV_IP:5555
```

执行固定的诊断验证项目，并把证据保存在电脑上的新目录：

```sh
python3 scripts/verify_tv.py --serial TV_IP:5555 --diagnostic --output results/session-01
```

若 `adb` 不在 PATH 中，可添加 `--adb /absolute/path/to/adb`。输出目录已存在时脚本拒绝覆盖。

脚本检查身份、域、capabilities、启动块设备可读性、策略加载节点可写性；每项使用独立随机日志标签并等待结果，缺失日志会报错。它不会执行任意用户输入命令、读取分区内容、写策略、安装程序、清日志或重启。诊断调用本身会更新原厂的运行时 `vendor.misysdiagnose.cmd.*` 参数并产生系统日志，因此不是完全零副作用的查询。

## 4. 手动验证临时 UID 0

在已核对的设备上执行：

```sh
adb -s TV_IP:5555 shell "service call TvService 4400 s16 s s16 '/system/bin/id | /system/bin/log -t TVRootProof'"
adb -s TV_IP:5555 shell 'logcat -d -v brief -s TVRootProof:I *:S'
```

日志可能需要短暂等待。再次测试时应换一个新标签，以免误读以前的结果。预期证据是：

```text
uid=0(root) gid=0(root) groups=0(root) context=u:r:misysdiagnose:s0
```

Binder 返回 `Result: Parcel(00000000 ...)` **只表示调用返回，不能单独证明命令执行成功**。必须核对本次唯一标签下的真实输出。

### 原理

本机 framework 的 `mitv.internal.TvServiceDefaultImpl.handleMitvServiceMiSysDiagnose` 读取两个字符串，分别设置诊断命令参数及命令代码。交易号 `4400` 对应此处理路径；代码 `s` 是本机已验证的短命令入口。原机 init 配置存在：

```text
on property:vendor.misysdiagnose.cmd.code=*
   exec - root root -- /vendor/bin/misysdiagnose -${vendor.misysdiagnose.cmd.code} ${vendor.misysdiagnose.cmd.arguments}
```

init 以 root 用户启动程序，SELinux 同时把它放入 `misysdiagnose` 域。因此每次执行的是受约束的短命令，不是持续开放的管理员会话。参数受 Android 属性长度限制，本项目按 **UTF-8 最多 91 字节**检查完整命令，包含管道及日志标签。长脚本和复杂嵌套引号并未作为稳定接口验证。

## 5. 当前能做与不能做的事

| 项目 | 当前证据 |
|---|---|
| 执行诊断 UID 0 命令 | 已验证 |
| 查看本进程身份、capabilities | 已验证；CapPrm/CapEff/CapBnd 为 `0000003fffffffff` |
| 读取诊断程序本体 | 已验证；26,656 字节，导出后完整哈希一致 |
| 访问 `/data/local/tmp` 中的脚本 | 从诊断域访问被拒绝，不能把普通 adb push 的脚本当作可执行 Root 脚本 |
| 读取原始启动块设备 | 已实测拒绝；`boot_a` 当前指向 `mmcblk0p25`，不得把这个编号套用到别的版本 |
| 加载 SELinux 策略 | 节点可写性检查失败，离线策略没有对应允许规则 |
| 任意切换为 init 域 / root adbd / su | 未取得 |
| Google Play 的系统特权集成 | 当前通道不足；ADB 安装普通 APK 不等于获得 signature/privileged 权限 |
| Magisk / 永久 Root | 未部署，启动分区未修改 |
| 原始分区镜像备份 | **未完成** |

Linux capabilities 和 UID 0 不能代替 SELinux 授权；Android 对 Root 进程同样执行强制访问控制。[AOSP 说明](https://source.android.com/docs/security/features/selinux)

## 6. SELinux 后续研究

2026-10-24 分析了本机 4 份策略 CIL 与 3 份 Android 34.0 映射，展开类型属性后仍未找到可直接读取块设备或加载策略的通路。确实存在 `crash_dump` 和 `netutils_wrapper` 两条受限转换，但这不代表能在目标域任意执行代码。内核配置也排除了依赖 USER_NS、DEVMEM 和相关 CRYPTO_USER_API 的路线。

详细证据、局限和未完成项见 [SELinux 研究记录](docs/selinux-research.md)。这份有限范围的分析不证明所有漏洞都不存在，也不能用内核版本号判断厂商是否回补了补丁。

如果以后取得能够读取原始分区的临时权限，先按 [备份验收标准](docs/backup-checklist.md) 保存原始镜像。未完成备份前，本项目没有提供任何分区写入步骤。

## 7. 收尾与常见误判

- 再次执行普通 `adb shell id` 仍是 shell 用户，是预期结果。
- `getenforce` 仍为 Enforcing，是当前已验证状态。
- 没有常驻 `su` 服务；不需要安装卸载模块来撤销本项目的验证。脚本不会设置 `persist.*`、开机服务或改系统分区。
- 诊断标签没有输出时，先检查设备是否在线和日志是否晚到，不要仅根据 Binder 返回值宣布成功。
- `Permission denied` 不能靠重复 `dd`、更换输出目录或把文件后缀改成 `.img` 解决。
- APK、配置 ZIP、CIL 文件及诊断 ELF 都不是原始固件备份。零字节、截断或未经校验的文件也不能当成救砖镜像。

本轮未重启、清数据、切槽、解锁、刷机、改 SELinux 标签或持久系统配置。测试日志和原厂运行时诊断参数会保留在系统通常的生命周期内。

## 8. 证据与参考

- [本机脱敏验证摘要](evidence/verified-2026-10-24.json)
- [AOSP：SELinux 与 Root 的权限边界](https://source.android.com/docs/security/features/selinux)
- [AOSP：策略、文件标签、属性标签和 Binder 服务标签](https://source.android.com/docs/security/features/selinux/implement)

原机程序只作本地分析，未随仓库分发。本文中的状态针对表格中的具体构建，不是任何型号的通用一键 Root 承诺。
