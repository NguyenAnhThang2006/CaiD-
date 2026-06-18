import re

class VOVTrafficParser:
    def __init__(self):
        # A set of predefined traffic text reports characteristic of Vietnamese traffic
        self.sample_reports = [
            {
                "text": "Ngã Tư Sở đang kẹt cứng, các phương tiện nhích từng chút một dưới mưa lớn.",
                "target": "Nga Tu So",
                "rules": (0.05, 0.45, 0.5) # P, N, n
            },
            {
                "text": "Đường Nguyễn Chí Thanh thông thoáng, xe cộ di chuyển nhanh chóng, dễ dàng.",
                "target": "Nguyen Chi Thanh",
                "rules": (0.8, 0.1, 0.1)
            },
            {
                "text": "Đường Láng mật độ giao thông đông đúc, di chuyển chậm, có hiện tượng ùn ứ nhẹ.",
                "target": "Duong Lang",
                "rules": (0.35, 0.35, 0.3)
            },
            {
                "text": "Trục đường Cầu Giấy xe đông nhưng di chuyển ổn định, chưa có ùn tắc.",
                "target": "Cau Giay",
                "rules": (0.6, 0.2, 0.2)
            },
            {
                "text": "Đường La Thành ùn tắc kéo dài do có xe buýt chết máy chắn ngang đường.",
                "target": "La Thanh",
                "rules": (0.05, 0.25, 0.7)
            },
            {
                "text": "Khu vực Xã Đàn thông thoáng cả hai chiều, phương tiện lưu thông thuận lợi.",
                "target": "Xa Dan",
                "rules": (0.85, 0.05, 0.1)
            },
            {
                "text": "Đường Trường Chinh ùn ứ cục bộ tại lối lên cầu cạn, dòng xe di chuyển chậm chạp.",
                "target": "Truong Chinh",
                "rules": (0.25, 0.35, 0.4)
            },
            {
                "text": "Trực quan nút giao Kim Mã lúc này khá vắng vẻ, các phương tiện lưu thông trơn tru.",
                "target": "Kim Ma",
                "rules": (0.8, 0.1, 0.1)
            },
            {
                "text": "Đường Đại Cồ Việt mưa phùn ẩm ướt, mặt đường trơn trượt, người lái xe di chuyển rất đắn đo.",
                "target": "Dai Co Viet",
                "rules": (0.4, 0.5, 0.1)
            }
        ]
        
        # Keyword-based parsing rules (Regex patterns for fallback rule-based parsing)
        self.keywords_negative = [
            (r"kẹt cứng|tắc nghẽn|ùn tắc kéo dài|đông cứng|va chạm|tai nạn", 0.7),
            (r"ùn ứ|di chuyển khó khăn|di chuyển chậm|chậm chạp|xe đông", 0.4),
            (r"mật độ đông|đông đúc|ùn cục bộ", 0.3)
        ]
        self.keywords_neutral = [
            (r"mưa lớn|mưa rào|ngập lụt|trơn trượt|thời tiết xấu", 0.45),
            (r"mưa phùn|ẩm ướt|đắn đo|lưỡng lự|rụt rè|chưa rõ ràng", 0.35),
            (r"đông nhưng vẫn di chuyển được|chậm nhưng ổn định", 0.25)
        ]
        self.keywords_positive = [
            (r"thông thoáng|vắng vẻ|thuận lợi|trơn tru|nhanh chóng|dễ dàng|lưu thông tốt", 0.8),
            (r"bình thường|ổn định|lưu thông ổn định|chưa có ùn tắc", 0.6)
        ]

    def get_all_samples(self):
        """Returns the list of sample traffic text reports."""
        return self.sample_reports

    def parse_text_locally(self, text):
        """
        Parses Vietnamese traffic text using regex heuristics.
        Returns a tuple of (P, N, n) fuzzy values.
        """
        # Default baseline values (equal split, high neutral)
        p_val = 0.33
        n_val = 0.34
        neg_val = 0.33
        
        # Check negative keywords
        for pattern, score in self.keywords_negative:
            if re.search(pattern, text, re.IGNORECASE):
                neg_val = score
                p_val = max(0.05, 1.0 - neg_val - 0.2)
                break
                
        # Check neutral keywords
        for pattern, score in self.keywords_neutral:
            if re.search(pattern, text, re.IGNORECASE):
                n_val = score
                break
                
        # Check positive keywords
        for pattern, score in self.keywords_positive:
            if re.search(pattern, text, re.IGNORECASE):
                p_val = score
                neg_val = max(0.05, 1.0 - p_val - 0.1)
                break
                
        # Adjust sum constraints
        tot = p_val + n_val + neg_val
        if tot > 1.0:
            p_val /= tot
            n_val /= tot
            neg_val /= tot
            
        return round(p_val, 2), round(n_val, 2), round(neg_val, 2)
