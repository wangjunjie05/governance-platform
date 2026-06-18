package com.example.governance;

import com.example.governance.config.RuleConfig;
import com.example.governance.config.RuleConfigLoader;
import com.example.governance.model.ScanResult;
import com.example.governance.parser.ProjectScanner;
import com.google.gson.Gson;
import com.google.gson.GsonBuilder;

import java.io.OutputStreamWriter;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.Paths;

/**
 * Java 扫描器命令行入口。
 *
 * 参数：
 * --source-path  Java 项目源码目录
 * --project-name 项目名称
 * --output-json  扫描结果 JSON 输出路径
 * --config-json  规则配置文件路径，可不传；不传时使用内置保守默认配置
 */
public class Main {
    public static void main(String[] args) throws Exception {
        CliArgs cliArgs = CliArgs.parse(args);
        if (cliArgs.sourcePath == null || cliArgs.outputJson == null) {
            System.err.println("Usage: java -jar scanner.jar --source-path <path> --project-name <name> --output-json <file> [--config-json <file>]");
            System.exit(2);
        }

        Path sourcePath = Paths.get(cliArgs.sourcePath).toAbsolutePath().normalize();
        String projectName = cliArgs.projectName == null || cliArgs.projectName.trim().isEmpty()
                ? sourcePath.getFileName().toString()
                : cliArgs.projectName.trim();

        Path configPath = cliArgs.configJson == null ? null : Paths.get(cliArgs.configJson).toAbsolutePath().normalize();
        RuleConfig ruleConfig = RuleConfigLoader.load(configPath);

        ProjectScanner scanner = new ProjectScanner(ruleConfig, configPath);
        ScanResult result = scanner.scan(projectName, sourcePath);

        Path outputJson = Paths.get(cliArgs.outputJson).toAbsolutePath().normalize();
        Files.createDirectories(outputJson.getParent());
        Gson gson = new GsonBuilder().disableHtmlEscaping().setPrettyPrinting().create();
        try (OutputStreamWriter writer = new OutputStreamWriter(Files.newOutputStream(outputJson), StandardCharsets.UTF_8)) {
            gson.toJson(result, writer);
        }
    }

    private static class CliArgs {
        String sourcePath;
        String projectName;
        String outputJson;
        String configJson;

        static CliArgs parse(String[] args) {
            CliArgs cliArgs = new CliArgs();
            for (int i = 0; i < args.length; i++) {
                String arg = args[i];
                String value = i + 1 < args.length ? args[i + 1] : null;
                if ("--source-path".equals(arg)) {
                    cliArgs.sourcePath = value;
                    i++;
                } else if ("--project-name".equals(arg)) {
                    cliArgs.projectName = value;
                    i++;
                } else if ("--output-json".equals(arg)) {
                    cliArgs.outputJson = value;
                    i++;
                } else if ("--config-json".equals(arg)) {
                    cliArgs.configJson = value;
                    i++;
                }
            }
            return cliArgs;
        }
    }
}
