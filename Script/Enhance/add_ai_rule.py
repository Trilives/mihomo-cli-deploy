import json
import os
import re

def auto_update_config_no_deps(file_path):
    # 1. 读取 YAML 文件
    # 注意：因为没有 yaml 库，我们只能进行简单的字符串/正则表达式处理
    # 或者利用 Mihomo/Clash 支持 JSON 格式的特性
    if not os.path.exists(file_path):
        print(f"找不到文件: {file_path}")
        return

    with open(file_path, 'r', encoding='utf-8') as f:
        content = f.read()

    # --- 逻辑说明 ---
    # 由于不使用 yaml 库，解析复杂的 YAML 非常困难且容易出错。
    # 这里我们采用一种“最安全”的字符串处理方式：
    # 我们只通过正则寻找 proxies 列表，提取节点名，然后直接生成新的配置块。

    # 提取所有节点名 (寻找以 - name: 开头的行)
    proxies_names = re.findall(r'-\s*name:\s*["\']?(.*?)["\']?\s*\n', content)
    
    if not proxies_names:
        print("未能在配置文件中匹配到节点，请检查格式是否标准。")
        return

    # 2. 筛选非港台节点
    exclude_keywords = ['香港', 'HK', 'Taiwan', '台湾', 'TW', '🇭🇰', '🇹🇼']
    ai_proxies = [
        name for name in proxies_names 
        if not any(key.upper() in name.upper() for key in exclude_keywords)
    ]

    if not ai_proxies:
        print("未找到符合条件的 AI 节点。")
        return

    # 3. 构造 "AI使用" 策略组字符串 (YAML 格式)
    ai_proxies_str = "\n".join([f"      - \"{name}\"" for name in ai_proxies])
    ai_group_yaml = f"""
  - name: "AI使用"
    type: fallback
    url: "http://www.gstatic.com/generate_204"
    interval: 300
    proxies:
{ai_proxies_str}
"""

    # 4. 插入到配置文件
    # 我们寻找 proxy-groups: 关键字，并在其下方插入
    if 'proxy-groups:' in content:
        # 避免重复添加
        if '"AI使用"' not in content and "'AI使用'" not in content:
            content = content.replace('proxy-groups:', f'proxy-groups:{ai_group_yaml}')
            print("已成功添加 'AI使用' 策略组。")
        else:
            print("'AI使用' 策略组已存在，跳过。")
    
    # 5. 将 "AI使用" 加入 "节点选择" 主组
    # 这里用正则查找 'name: "节点选择"' 所在的 proxies 块并插入
    # 注意：此逻辑较为依赖你的配置缩进格式
    main_group_pattern = r'(name:\s*["\']?节点选择["\']?[\s\S]*?proxies:\s*\n)'
    if re.search(main_group_pattern, content):
        if '      - "AI使用"' not in content:
            content = re.sub(main_group_pattern, r'\1      - "AI使用"\n', content)
            print("已将 'AI使用' 嵌入到 '节点选择' 中。")

    # 6. 添加 Rules 到最顶部
    ai_rules = [
        '  - DOMAIN-SUFFIX,openai.com,"AI使用"',
        '  - DOMAIN-SUFFIX,chatgpt.com,"AI使用"',
        '  - DOMAIN-KEYWORD,openai,"AI使用"',
        '  - DOMAIN-SUFFIX,claude.ai,"AI使用"'
    ]
    
    if 'rules:' in content:
        rules_header = "rules:\n"
        new_rules_str = rules_header + "\n".join(ai_rules) + "\n"
        if '"AI使用"' not in content.split('rules:')[1][:500]: # 简单判断顶部是否有规则
            content = content.replace(rules_header, new_rules_str)
            print("已添加 AI 分流规则到顶部。")

    # 7. 保存文件
    with open(file_path, 'w', encoding='utf-8') as f:
        f.write(content)
    print("修改保存成功！")

if __name__ == "__main__":
    # 自动识别你的 Ubuntu 路径
    config_path = os.path.expanduser('../../config.yaml')
    auto_update_config_no_deps(config_path)