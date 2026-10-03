# dfm_scanner.py
import gerber
from gerber.primitives import Line

def scan_track_width(copper_file_path, min_width_mm=0.15):
    """Quét các đường mạch có độ rộng nhỏ hơn ngưỡng cho phép."""
    violations = []
    try:
        cam_file = gerber.read(copper_file_path)
        for primitive in cam_file.primitives:
            if isinstance(primitive, Line):
                # Chuyển đổi Aperture size sang mm (nếu file gốc dùng inch)
                width = primitive.aperture.shape[0] if isinstance(primitive.aperture.shape, tuple) else primitive.aperture.shape
                unit_multiplier = 25.4 if cam_file.units == 'inch' else 1.0
                width_mm = width * unit_multiplier
                
                if width_mm < min_width_mm:
                    # Ghi nhận tọa độ trung tâm của đoạn mạch lỗi
                    mid_x = (primitive.start[0] + primitive.end[0]) / 2
                    mid_y = (primitive.start[1] + primitive.end[1]) / 2
                    violations.append({
                        "x": mid_x * unit_multiplier,
                        "y": mid_y * unit_multiplier,
                        "msg": f"Track width {width_mm:.3f}mm < {min_width_mm}mm"
                    })
    except Exception:
        pass
    return violations