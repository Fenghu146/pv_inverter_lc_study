/* 用 TI 官方生成器创建 LAUNCHXL-F28379D 目标配置（XDS110 + TMS320F28379D）
 * 运行: dss.bat gen_ccxml.js
 */
importPackage(Packages.com.ti.debug.engine.scripting);
importPackage(Packages.com.ti.ccstudio.scripting.environment);
importPackage(Packages.java.lang);

var env = ScriptingEnvironment.instance();
var server = env.getServer("DebugServer.1");

try {
    env.traceWrite("Generating Target Configuration file... ");
    var gen = server.createTargetConfigurationGenerator();
    gen.setOutputDirectory("C:/Users/35015/Desktop/大创/pv_inverter_lc_study/dsp/ccs/");
    gen.setConnection("Texas Instruments XDS110 USB Debug Probe");
    gen.setDevice("TMS320F28379D");
    gen.createConfiguration("pv_inverter_flash.ccxml");
    env.traceWrite("Generated OK.\n");
} catch (err) {
    env.traceWrite("Error: " + err + "\n");
}
server.stop();
