"""服务器端冒烟测试：验证 utils 函数能实际执行

为什么需要：静态分析抓不到无限递归。
曾踩过：patch 时把 _make_qr 的函数体误写成 return _make_qr(...)，
语法完全合法，只有运行时才炸 RecursionError。

在服务器上跑（需要 frappe 环境）：
    docker exec frappe_docker-backend-1 bash -c \
      'cd /home/frappe/frappe-bench/sites && \
       /home/frappe/frappe-bench/env/bin/python /tmp/smoke_test.py'
"""

import sys
import traceback

import frappe

failures = []


def check(label, fn):
    try:
        result = fn()
        print(f"  ✓ {label}: {result}")
    except RecursionError:
        print(f"  ✗ {label}: 无限递归！")
        failures.append(f"{label}: RecursionError")
        traceback.print_exc()
    except Exception as e:
        print(f"  ✗ {label}: {type(e).__name__}: {e}")
        failures.append(f"{label}: {type(e).__name__}: {e}")


def main():
    frappe.init(site="erp.motitoo.com")
    frappe.connect()

    print("════ utils 冒烟测试 ════")

    from secondtrade.utils.cost_allocation import (
        allocate_by_reference_price,
        calculate_capital_cost,
    )
    from secondtrade.utils.label_generator import (
        generate_qr_png,
        generate_serial_number,
        build_label_payload,
    )
    from secondtrade.utils.evidence_builder import build_evidence_package

    check("generate_serial_number",
          lambda: generate_serial_number("261003-01", "GPU", 1))

    check("generate_qr_png",
          lambda: f"{len(generate_qr_png('261003-01-GPU-01'))} bytes")

    check("generate_qr_png（超长 SN）",
          lambda: f"{len(generate_qr_png('X' * 200))} bytes")

    def alloc():
        class T:
            allocated_cost = 0.0

        ts = [T(), T(), T()]
        items = [{"market_ref_price_cny": p, "_target": t}
                 for p, t in zip([2000, 6000, 3000], ts)]
        ratio = allocate_by_reference_price(items, 9365.87)
        total = round(sum(t.allocated_cost for t in ts), 2)
        assert abs(total - 9365.87) < 0.01, f"分摊合计 {total} ≠ 9365.87"
        return f"ratio={ratio:.4f} 合计={total}"

    check("allocate_by_reference_price", alloc)
    check("calculate_capital_cost",
          lambda: f"{calculate_capital_cost(10000, '2026-10-01', '2026-10-31', 8)} CNY")

    check("build_label_payload",
          lambda: repr(build_label_payload("261003-01-GPU-01")))

    print()
    print("════ 结果 ════")
    if failures:
        print(f"✗ {len(failures)} 个失败：")
        for f in failures:
            print(f"  {f}")
        return 1
    print("✓ 全部通过")
    return 0


if __name__ == "__main__":
    sys.exit(main())
