# utils/armv8_monitor.py
"""
ARMv8性能监控和优化建议
"""

import time
import psutil
import threading
from typing import Dict, List, Optional
from dataclasses import dataclass

@dataclass
class ARM64PerformanceMetrics:
    """ARM64性能指标"""
    cpu_usage: float
    memory_usage: float
    cpu_frequency: Dict[int, float]  # 每个核心的频率
    temperature: Optional[float] = None  # CPU温度（如果可用）
    power_usage: Optional[float] = None  # 功耗估算（如果可用）
    armv8_features_used: List[str] = None

class ARM64PerformanceMonitor:
    """ARM64性能监控器"""
    
    def __init__(self, interval: int = 60):
        self.interval = interval  # 监控间隔（秒）
        self.metrics_history = []
        self.monitoring = False
        self.monitor_thread = None
        
    def start_monitoring(self):
        """开始性能监控"""
        if self.monitoring:
            return
        
        self.monitoring = True
        self.monitor_thread = threading.Thread(target=self._monitor_loop, daemon=True)
        self.monitor_thread.start()
        print(f"[监控] ARM64性能监控已启动，间隔: {self.interval}秒")
    
    def stop_monitoring(self):
        """停止性能监控"""
        self.monitoring = False
        if self.monitor_thread:
            self.monitor_thread.join(timeout=5)
    
    def _monitor_loop(self):
        """监控循环"""
        while self.monitoring:
            try:
                metrics = self.collect_metrics()
                self.metrics_history.append(metrics)
                
                # 保留最近100条记录
                if len(self.metrics_history) > 100:
                    self.metrics_history = self.metrics_history[-100:]
                
                # 检查性能问题
                self._check_performance_issues(metrics)
                
            except Exception as e:
                print(f"[监控错误] {e}")
            
            time.sleep(self.interval)
    
    def collect_metrics(self) -> ARM64PerformanceMetrics:
        """收集性能指标"""
        cpu_percent = psutil.cpu_percent(interval=1)
        memory = psutil.virtual_memory()
        
        # 获取CPU频率（ARM大小核可能有不同频率）
        cpu_freq = {}
        try:
            if hasattr(psutil, 'cpu_freq') and psutil.cpu_freq(percpu=True):
                freqs = psutil.cpu_freq(percpu=True)
                for i, freq in enumerate(freqs):
                    if freq and hasattr(freq, 'current'):
                        cpu_freq[i] = freq.current
        except Exception:
            pass
        
        # 获取温度（ARM Linux通常有）
        temperature = None
        try:
            if hasattr(psutil, 'sensors_temperatures'):
                temps = psutil.sensors_temperatures()
                if temps and 'cpu_thermal' in temps:
                    temperature = temps['cpu_thermal'][0].current
        except Exception:
            pass
        
        return ARM64PerformanceMetrics(
            cpu_usage=cpu_percent,
            memory_usage=memory.percent,
            cpu_frequency=cpu_freq,
            temperature=temperature
        )
    
    def _check_performance_issues(self, metrics: ARM64PerformanceMetrics):
        """检查性能问题并给出建议"""
        warnings = []
        
        # CPU使用率过高警告
        if metrics.cpu_usage > 90:
            warnings.append(f"⚠️ CPU使用率过高: {metrics.cpu_usage:.1f}%")
        
        # 内存使用率过高警告
        if metrics.memory_usage > 90:
            warnings.append(f"⚠️ 内存使用率过高: {metrics.memory_usage:.1f}%")
        
        # 温度过高警告
        if metrics.temperature and metrics.temperature > 80:
            warnings.append(f"⚠️ CPU温度过高: {metrics.temperature:.1f}°C")
        
        if warnings:
            print("[性能警告] " + " | ".join(warnings))
    
    def get_performance_summary(self) -> Dict:
        """获取性能摘要"""
        if not self.metrics_history:
            return {}
        
        latest = self.metrics_history[-1]
        
        # 计算平均频率（区分大小核）
        freqs = list(latest.cpu_frequency.values())
        avg_freq = sum(freqs) / len(freqs) if freqs else 0
        
        # 识别大小核模式（ARM常见）
        if freqs:
            max_freq = max(freqs)
            min_freq = min(freqs)
            big_little_ratio = max_freq / min_freq if min_freq > 0 else 1
        else:
            big_little_ratio = 1
        
        return {
            "cpu_usage_percent": latest.cpu_usage,
            "memory_usage_percent": latest.memory_usage,
            "avg_cpu_frequency_mhz": avg_freq,
            "temperature_c": latest.temperature,
            "big_little_ratio": big_little_ratio,
            "metrics_count": len(self.metrics_history)
        }
    
    def get_optimization_recommendations(self) -> List[str]:
        """获取优化建议（基于ARM64架构）"""
        recommendations = []
        
        if not self.metrics_history:
            return recommendations
        
        summary = self.get_performance_summary()
        
        # CPU相关建议
        if summary.get("cpu_usage_percent", 0) > 80:
            recommendations.append("🔧 建议调整线程池大小，减少并发任务")
        
        # 内存相关建议
        if summary.get("memory_usage_percent", 0) > 85:
            recommendations.append("🔧 建议增加Docker容器内存限制或优化内存使用")
        
        # 温度相关建议（ARM设备可能对温度敏感）
        if summary.get("temperature_c", 0) > 70:
            recommendations.append("🔧 建议改善散热或降低CPU频率")
        
        # ARM特定优化建议
        recommendations.append("🎯 启用ARMv8 CRC32硬件加速（如果CPU支持）")
        recommendations.append("🎯 使用NEON SIMD优化的图像处理库")
        recommendations.append("🎯 调整OpenBLAS线程数以匹配ARM核心数")
        
        return recommendations


# 全局监控器实例
arm64_monitor = ARM64PerformanceMonitor(interval=300)  # 5分钟间隔