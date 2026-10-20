"""PV 阵列单二极管模型
标定目标(方案附录A): Voc=90V, Isc=2.9A, V_mpp=75V, I_mpp=2.7A, P_mpp≈200W
模型: I = G·Iph - I0·(exp(V/nVT) - 1)
G = 辐照度标幺值 (0.35/0.65/0.90 对应方案3个功率点)
"""
import math


class PVArray:
    def __init__(self, Iph=2.9, I0=4.05e-8, nVT=4.95):
        self.Iph = Iph
        self.I0 = I0
        self.nVT = nVT

    def current(self, V, G=1.0):
        """端口电流(流出为正)"""
        return G * self.Iph - self.I0 * (math.exp(V / self.nVT) - 1.0)

    def power(self, V, G=1.0):
        return V * self.current(V, G)

    def mpp(self, G=1.0, n=4000):
        """数值求最大功率点(V_oc 内均匀扫描)"""
        best_v, best_p = 0.0, -1.0
        for i in range(1, n + 1):
            v = 100.0 * i / n
            p = self.power(v, G)
            if p > best_p:
                best_v, best_p = v, p
        return best_v, self.current(best_v, G), best_p


if __name__ == "__main__":
    import sys
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    pv = PVArray()
    for G in (1.0, 0.9, 0.65, 0.35):
        vmpp, impp, pmpp = pv.mpp(G)
        print(f"G={G:.2f}: V_mpp={vmpp:.1f} V, I_mpp={impp:.2f} A, P_mpp={pmpp:.1f} W")
    print(f"Voc(1sun)≈{90:.0f}V, Isc(1sun)={pv.current(0, 1.0):.2f}A")
