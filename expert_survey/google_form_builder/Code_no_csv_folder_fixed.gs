/**
 * Auto-builds the VSL prescription gloss expert survey in Google Forms.
 *
 * How to use:
 * 1. Upload expert_survey/images/ to Google Drive as one folder.
 * 2. Copy that folder ID from the Drive URL.
 * 3. Paste it into IMAGE_FOLDER_ID below.
 * 4. Run createVslGlossSurvey() in Apps Script.
 */
const IMAGE_FOLDER_ID = 'PASTE_GOOGLE_DRIVE_IMAGE_FOLDER_ID_HERE';
const FORM_TITLE = 'VSL Prescription Gloss Expert Evaluation';

const QUESTIONS = [
  {
    "id": "Q001",
    "imageFile": "Q001.png",
    "gloss": "Dùng cho:\nthuốc số 1: bác sĩ kê thuốc + số 1 + Diệt vi khuẩn + Giúp bớt viêm + Dùng theo đơn bác sĩ\nthuốc số 2: bác sĩ kê thuốc + số 2 + giúp bạn + cảm thấy + dễ chịu hơn\nthuốc số 3: bác sĩ kê thuốc + số 3 + người bị cao huyết áp + người bị đau ngực do tim\n\nDùng như nào:\nthuốc số 1: uống + 2 viên + buổi sáng + và + 2 viên + buổi chiều + mỗi ngày\nthuốc số 2: uống + 1 viên + buổi sáng + và + 1 viên + buổi chiều + mỗi ngày\nthuốc số 3: uống + 1 viên + buổi sáng + mỗi ngày\n\nLưu ý:\nthuốc số 1: Uống sau ăn + Uống đủ liều + Không bỏ thuốc + Báo người lớn nếu mệt nhiều\nthuốc số 2: mỗi lần uống + cách nhau + 4-6 tiếng + không quá + 4 viên + mỗi ngày + uống nhiều + hại gan\nthuốc số 3: uống đúng giờ + không tự ý ngừng + cẩn thận chóng mặt"
  },
  {
    "id": "Q002",
    "imageFile": "Q002.png",
    "gloss": "Dùng cho:\nbác sĩ kê thuốc + số 1 + dùng cho người bị tiểu đường típ 2 + giúp hạ đường máu\n\nDùng như nào:\nuống + 1 viên + buổi sáng + mỗi ngày\n\nLưu ý:\nuống sau ăn + tránh rượu bia + báo bác sĩ nếu khó thở hoặc mệt lả"
  },
  {
    "id": "Q003",
    "imageFile": "Q003.png",
    "gloss": "Dùng cho:\nbác sĩ kê thuốc + số 1 + dùng cho người bị tiểu đường típ 2 + giúp hạ đường máu\n\nDùng như nào:\nuống + 1 viên + buổi sáng + mỗi ngày\n\nLưu ý:\nuống sau ăn + tránh rượu bia + báo bác sĩ nếu khó thở hoặc mệt lả"
  },
  {
    "id": "Q004",
    "imageFile": "Q004.png",
    "gloss": "Dùng cho:\nthuốc số 1: bác sĩ kê thuốc + số 1 + Giúp đi tiểu dễ hơn + Giúp hạ huyết áp\nthuốc số 2: bác sĩ kê thuốc + số 2 + trị nhiễm khuẩn + trị amip + trị Giardia\n\nDùng như nào:\nthuốc số 1: uống + 1 viên + buổi sáng + mỗi ngày\nthuốc số 2: uống + 2 viên + buổi sáng + và + 2 viên + buổi chiều + mỗi ngày\n\nLưu ý:\nthuốc số 1: Dễ chóng mặt + Đứng lên chậm + Ngất phải đi khám\nthuốc số 2: không uống rượu bia + uống đúng giờ + đủ liều + báo bác sĩ nếu có bệnh gan"
  },
  {
    "id": "Q005",
    "imageFile": "Q005.png",
    "gloss": "Dùng cho:\nthuốc số 1: bác sĩ kê thuốc + số 1 + Dùng cho nhiễm khuẩn do vi khuẩn.\nthuốc số 2: bác sĩ kê thuốc + số 2 + Dùng khi bác sĩ kê để giảm viêm và dị ứng nặng.\nthuốc số 3: bác sĩ kê thuốc + số 3 + giúp bạn + cảm thấy + dễ chịu hơn\n\nDùng như nào:\nthuốc số 1: uống + 2 viên + buổi sáng + và + 2 viên + buổi chiều + mỗi ngày\nthuốc số 2: uống + 2 viên + buổi sáng + mỗi ngày\nthuốc số 3: uống + 1 viên + buổi sáng + và + 1 viên + buổi chiều + mỗi ngày\n\nLưu ý:\nthuốc số 1: Uống đủ liều. Không tự ngưng.\nthuốc số 2: Không tự ngừng thuốc. Báo người lớn hoặc bác sĩ nếu thấy mệt nhiều, khó thở, đau bụng nặng.\nthuốc số 3: mỗi lần uống + cách nhau + 4-6 tiếng + không quá + 4 viên + mỗi ngày + uống nhiều + hại gan"
  },
  {
    "id": "Q006",
    "imageFile": "Q006.png",
    "gloss": "Dùng cho:\nbác sĩ kê thuốc + số 1 + Dùng cho người bị mỡ máu cao.\n\nDùng như nào:\nuống + 1 viên + buổi tối + mỗi ngày\n\nLưu ý:\nTheo dõi đau cơ, vàng da, đau bụng."
  },
  {
    "id": "Q007",
    "imageFile": "Q007.png",
    "gloss": "Dùng cho:\nthuốc số 1: bác sĩ kê thuốc + số 1 + kháng sinh + uống đúng giờ\nthuốc số 2: bác sĩ kê thuốc + số 2 + giúp bạn + cảm thấy + dễ chịu hơn\n\nDùng như nào:\nthuốc số 1: uống + 2 viên + buổi sáng + và + 2 viên + buổi tối + mỗi ngày\nthuốc số 2: uống + 1 viên + buổi sáng + và + 1 viên + buổi tối + mỗi ngày\n\nLưu ý:\nthuốc số 1: dị ứng + phát ban + bệnh thận\nthuốc số 2: mỗi lần uống + cách nhau + 4-6 tiếng + không quá + 4 viên + mỗi ngày + uống nhiều + hại gan"
  },
  {
    "id": "Q008",
    "imageFile": "Q008.png",
    "gloss": "Dùng cho:\nthuốc số 1: bác sĩ kê thuốc + số 1 + người bị cao huyết áp\nthuốc số 2: bác sĩ kê thuốc + số 2 + người bị bệnh tâm thần phân liệt + người bị rối loạn lưỡng cực + người cần ổn định suy nghĩ và cảm xúc\n\nDùng như nào:\nthuốc số 1: uống + 1 viên + buổi sáng + mỗi ngày\nthuốc số 2: uống + 1 viên + buổi tối + mỗi ngày\n\nLưu ý:\nthuốc số 1: không dùng cho phụ nữ có thai + có thể gây chóng mặt + báo bác sĩ nếu sưng mặt hoặc khó thở\nthuốc số 2: uống đúng giờ + không tự ngừng + có thể gây buồn ngủ + báo bác sĩ khi có dấu hiệu nặng"
  },
  {
    "id": "Q009",
    "imageFile": "Q009.png",
    "gloss": "Dùng cho:\nthuốc số 1: bác sĩ kê thuốc + số 1 + Người bị tiểu đường típ 2 + Người cần giảm đường máu\nthuốc số 2: bác sĩ kê thuốc + số 2 + Dùng cho người bị tiểu đường típ 2.\nthuốc số 3: bác sĩ kê thuốc + số 3 + Người hay chóng mặt + Người đau đầu do tuần hoàn não kém + Người giảm trí nhớ nhẹ\n\nDùng như nào:\nthuốc số 1: uống + 1 viên + buổi trưa + và + 1 viên + buổi tối + mỗi ngày\nthuốc số 2: uống + 3 viên + buổi sáng + mỗi ngày\nthuốc số 3: uống + 2 viên + buổi sáng + và + 2 viên + buổi chiều + mỗi ngày\n\nLưu ý:\nthuốc số 1: Uống sau ăn + Theo dõi đường máu + Tránh rượu + Cẩn thận nếu bệnh thận\nthuốc số 2: Có thể làm đường trong máu xuống quá thấp nếu bỏ bữa.\nthuốc số 3: Uống đúng liều + Không tự ý dùng chung với thuốc loãng máu + Báo ngay khi có chảy máu"
  },
  {
    "id": "Q010",
    "imageFile": "Q010.png",
    "gloss": "Dùng cho:\nthuốc số 1: bác sĩ kê thuốc + số 1 + đau họng + giảm\nthuốc số 2: bác sĩ kê thuốc + số 2 + giúp bạn + cảm thấy + dễ chịu hơn\nthuốc số 3: bác sĩ kê thuốc + số 3 + dễ thở hơn + bớt ho + bớt hắt hơi + bớt sổ mũi\n\nDùng như nào:\nthuốc số 1: uống + 2 viên + buổi sáng + và + 2 viên + buổi chiều + mỗi ngày\nthuốc số 2: uống + 2 viên + buổi sáng + và + 2 viên + buổi chiều + mỗi ngày\nthuốc số 3: uống + 1 viên + buổi tối + mỗi ngày\n\nLưu ý:\nthuốc số 1: BẮT BUỘC + uống hết + đơn thuốc + KHÔNG + dừng thuốc sớm + có thể + tiêu chảy\nthuốc số 2: mỗi lần uống + cách nhau + 4-6 tiếng + không quá + 4 viên + mỗi ngày + uống nhiều + hại gan\nthuốc số 3: không cắt cơn hen cấp + uống đúng liều + báo bác sĩ khi có dấu hiệu lạ"
  },
  {
    "id": "Q011",
    "imageFile": "Q011.jpg",
    "gloss": "Dùng cho:\nbác sĩ kê thuốc + số 1 + Trị giun + Trị sán\n\nDùng như nào:\nuống + 40 viên + mỗi ngày\n\nLưu ý:\nUống sau ăn + Đúng liều + Báo bác sĩ nếu có dấu hiệu lạ"
  },
  {
    "id": "Q012",
    "imageFile": "Q012.jpg",
    "gloss": "Dùng cho:\nbác sĩ kê thuốc + số 1 + bụng khỏe hơn + giảm tiêu chảy + giảm đầy bụng\n\nDùng như nào:\nuống + 10 viên + mỗi ngày\n\nLưu ý:\ndị ứng + sốt cao + mất nước"
  },
  {
    "id": "Q013",
    "imageFile": "Q013.jpg",
    "gloss": "Dùng cho:\nthuốc số 1: bác sĩ kê thuốc + số 1 + Người bị trào ngược dạ dày + Người bị viêm loét dạ dày + Người có nhiều axit dạ dày\nthuốc số 2: bác sĩ kê thuốc + số 2 + Dùng cho người bị loét hoặc viêm dạ dày.\nthuốc số 3: bác sĩ kê thuốc + số 3 + trẻ thiếu canxi + trẻ cần bổ sung canxi + trẻ cần vitamin D\n\nDùng như nào:\nthuốc số 1: uống + 01 viên + buổi sáng + mỗi ngày\nthuốc số 2: uống + 60 viên + buổi sáng + và + 60 viên + buổi tối + mỗi ngày\nthuốc số 3: uống + 01 viên + buổi sáng + và + 01 viên + buổi tối + mỗi ngày\n\nLưu ý:\nthuốc số 1: Uống trước ăn + Không tự dùng lâu ngày + Báo bác sĩ nếu có dấu hiệu nặng\nthuốc số 2: Uống khi bụng rỗng. Uống xa thuốc khác.\nthuốc số 3: uống sau ăn + không quá liều + báo bác sĩ nếu dị ứng"
  },
  {
    "id": "Q014",
    "imageFile": "Q014.jpg",
    "gloss": "Dùng cho:\nthuốc số 1: bác sĩ kê thuốc + số 1 + Họng + Tai + Mũi + Phổi + Da\nthuốc số 2: bác sĩ kê thuốc + số 2 + người cần tránh thai theo chỉ định bác sĩ\nthuốc số 3: bác sĩ kê thuốc + số 3 + Giảm sưng + Giảm đỏ + Giảm ngứa + Giảm dị ứng\n\nDùng như nào:\nthuốc số 1: uống + 1 viên + mỗi ngày\nthuốc số 2: uống + 7 viên + mỗi ngày\nthuốc số 3: uống + 6 viên + mỗi ngày\n\nLưu ý:\nthuốc số 1: Uống đúng liều + Uống đủ ngày + Không tự ngưng + Báo người lớn nếu mệt nhiều\nthuốc số 2: uống đúng giờ mỗi ngày + không ngừa bệnh lây tình dục + đi khám nếu có dấu hiệu nặng\nthuốc số 3: Không tự ngưng + Uống sau ăn + Báo bác sĩ nếu mệt nhiều"
  },
  {
    "id": "Q015",
    "imageFile": "Q015.jpg",
    "gloss": "Dùng cho:\nthuốc số 1: bác sĩ kê thuốc + số 1 + Trẻ bị bệnh do vi khuẩn + Dùng theo toa bác sĩ\nthuốc số 2: bác sĩ kê thuốc + số 2 + giúp bụng khỏe + giảm tiêu chảy + hỗ trợ tiêu hóa\n\nDùng như nào:\nthuốc số 1: uống + 10 viên + mỗi ngày\nthuốc số 2: uống + 10 viên + mỗi ngày\n\nLưu ý:\nthuốc số 1: Uống đúng giờ + Uống đủ số ngày + Không tự ngưng + Đi khám nếu khó thở hoặc nổi mẩn nhiều\nthuốc số 2: uống sau ăn + uống đủ nước + đi khám nếu nặng"
  },
  {
    "id": "Q016",
    "imageFile": "Q016.jpg",
    "gloss": "Dùng cho:\nthuốc số 1: bác sĩ kê thuốc + số 1 + uống sau ăn + đúng giờ + đủ liều + lắc kỹ\nthuốc số 2: bác sĩ kê thuốc + số 2 + Dùng cho bé bị khò khè, co thắt phế quản.\nthuốc số 3: bác sĩ kê thuốc + số 3 + người bị dị ứng + người bị ngứa + người bị nổi mẩn\nthuốc số 4: bác sĩ kê thuốc + số 4 + Trẻ hay ốm vặt + Trẻ dễ viêm mũi họng + Trẻ sức đề kháng yếu\n\nDùng như nào:\nthuốc số 1: uống + 1 viên + mỗi ngày\nthuốc số 2: uống + 10 viên + mỗi ngày\nthuốc số 3: uống + 1 viên + mỗi ngày\nthuốc số 4: uống + 1 viên + buổi sáng + mỗi ngày\n\nLưu ý:\nthuốc số 1: dị ứng thuốc + không trị virus + theo dõi tiêu chảy + đủ liệu trình\nthuốc số 2: Có thể làm run tay, tim đập nhanh. Nếu nặng hơn, đi khám ngay.\nthuốc số 3: có thể buồn ngủ + uống đúng liều + đi khám nếu nặng\nthuốc số 4: Uống đúng theo bác sĩ + Không tự ý tăng liều + Đi khám ngay nếu khó thở hoặc sưng mặt"
  },
  {
    "id": "Q017",
    "imageFile": "Q017.jpg",
    "gloss": "Dùng cho:\nthuốc số 1: bác sĩ kê thuốc + số 1 + viêm họng + viêm tai + viêm xoang + viêm phổi + nhiễm khuẩn da + nhiễm khuẩn răng + nhiễm khuẩn tiểu\nthuốc số 2: bác sĩ kê thuốc + số 2 + Bé bị nhiễm khuẩn do vi khuẩn + Dùng theo đơn bác sĩ + Thuốc không trị cúm hay cảm do virus\nthuốc số 3: bác sĩ kê thuốc + số 3 + Dùng cho bé bị dị ứng.\nthuốc số 4: bác sĩ kê thuốc + số 4 + Bụng khó chịu + Ăn khó tiêu + Đi ngoài nhẹ\n\nDùng như nào:\nthuốc số 1: uống + 14 viên + mỗi ngày\nthuốc số 2: uống + 1 viên + buổi sáng + mỗi ngày\nthuốc số 3: uống + 1 viên + buổi sáng + và + 1 viên + buổi tối + mỗi ngày\nthuốc số 4: uống + 7 viên + mỗi ngày\n\nLưu ý:\nthuốc số 1: uống sau ăn + uống đủ liều + không tự ngừng + tránh nếu dị ứng penicillin + đi khám nếu khó thở\nthuốc số 2: Uống đủ liều + Uống đúng giờ + Không tự ngưng thuốc + Đi khám ngay nếu khó thở hoặc nổi ban nhiều\nthuốc số 3: Có thể gây buồn ngủ. Dùng đúng liều.\nthuốc số 4: Đọc kỹ nhãn + Dùng đúng liều + Ngưng nếu dị ứng"
  },
  {
    "id": "Q018",
    "imageFile": "Q018.jpg",
    "gloss": "Dùng cho:\nthuốc số 1: bác sĩ kê thuốc + số 1 + viêm họng + viêm tai + viêm xoang + viêm phổi + nhiễm khuẩn da + nhiễm khuẩn răng + nhiễm khuẩn tiểu\nthuốc số 2: bác sĩ kê thuốc + số 2 + trẻ bị nhiễm khuẩn + viêm họng + viêm tai + viêm phổi\nthuốc số 3: bác sĩ kê thuốc + số 3 + Dùng cho bé bị dị ứng.\nthuốc số 4: bác sĩ kê thuốc + số 4 + Bụng khó chịu + Ăn khó tiêu + Đi ngoài nhẹ\n\nDùng như nào:\nthuốc số 1: uống + 21 viên + buổi sáng + và + 21 viên + buổi tối + mỗi ngày\nthuốc số 2: uống + 1 viên + buổi sáng + mỗi ngày\nthuốc số 3: uống + 1 viên + buổi sáng + và + 1 viên + buổi tối + mỗi ngày\nthuốc số 4: uống + 7 viên + mỗi ngày\n\nLưu ý:\nthuốc số 1: uống sau ăn + uống đủ liều + không tự ngừng + tránh nếu dị ứng penicillin + đi khám nếu khó thở\nthuốc số 2: uống đúng liều + lắc kỹ + uống đủ ngày + không tự ngừng\nthuốc số 3: Có thể gây buồn ngủ. Dùng đúng liều.\nthuốc số 4: Đọc kỹ nhãn + Dùng đúng liều + Ngưng nếu dị ứng"
  },
  {
    "id": "Q019",
    "imageFile": "Q019.jpg",
    "gloss": "Dùng cho:\nbác sĩ kê thuốc + số 1 + người thiếu sắt + người thiếu máu do thiếu sắt\n\nDùng như nào:\nuống + 1 viên + buổi sáng + mỗi ngày\n\nLưu ý:\nuống đúng liều + không tự uống thêm + để xa trẻ em"
  },
  {
    "id": "Q020",
    "imageFile": "Q020.jpg",
    "gloss": "Dùng cho:\nthuốc số 1: bác sĩ kê thuốc + số 1 + viêm họng + viêm tai + viêm xoang + viêm phổi + nhiễm khuẩn da + nhiễm khuẩn răng + nhiễm khuẩn tiểu\nthuốc số 2: bác sĩ kê thuốc + số 2 + Giảm sưng + Giảm đỏ + Giảm ngứa + Giảm dị ứng\nthuốc số 3: bác sĩ kê thuốc + số 3 + giảm kích động + giúp bình tĩnh + ổn định hành vi\nthuốc số 4: bác sĩ kê thuốc + số 4 + Bụng khó chịu + Ăn khó tiêu + Đi ngoài nhẹ\n\nDùng như nào:\nthuốc số 1: uống + 21 viên + mỗi ngày\nthuốc số 2: uống + 15 viên + mỗi ngày\nthuốc số 3: uống + 10 viên + mỗi ngày\nthuốc số 4: uống + 7 viên + mỗi ngày\n\nLưu ý:\nthuốc số 1: uống sau ăn + uống đủ liều + không tự ngừng + tránh nếu dị ứng penicillin + đi khám nếu khó thở\nthuốc số 2: Không tự ngưng + Uống sau ăn + Báo bác sĩ nếu mệt nhiều\nthuốc số 3: uống đúng giờ + không tự ngừng + theo dõi sốt cao + theo dõi co giật + cẩn thận buồn ngủ\nthuốc số 4: Đọc kỹ nhãn + Dùng đúng liều + Ngưng nếu dị ứng"
  },
  {
    "id": "Q021",
    "imageFile": "Q021.jpg",
    "gloss": "Dùng cho:\nthuốc số 1: bác sĩ kê thuốc + số 1 + giảm + nguy cơ + cao huyết áp\nthuốc số 2: bác sĩ kê thuốc + số 2 + Dùng cho người bị mỡ máu cao.\n\nDùng như nào:\nthuốc số 1: uống + 1 viên + buổi sáng + mỗi ngày\nthuốc số 2: uống + 1 viên + buổi tối + mỗi ngày\n\nLưu ý:\nthuốc số 1: uống + đều đặn + mỗi ngày + không + tự ý + ngừng thuốc\nthuốc số 2: Không dùng cho phụ nữ có thai. Báo bác sĩ nếu đau cơ hoặc vàng da."
  },
  {
    "id": "Q022",
    "imageFile": "Q022.jpg",
    "gloss": "Dùng cho:\nthuốc số 1: bác sĩ kê thuốc + số 1 + Dùng cho người bị tiểu đường típ 2.\nthuốc số 2: bác sĩ kê thuốc + số 2 + Dùng cho người bị mỡ máu cao.\nthuốc số 3: bác sĩ kê thuốc + số 3 + giảm đau tê rát + giảm lo âu + hỗ trợ chống co giật\n\nDùng như nào:\nthuốc số 1: uống + 1 viên + buổi sáng + mỗi ngày\nthuốc số 2: uống + 1 viên + buổi tối + mỗi ngày\nthuốc số 3: uống + 1 viên + mỗi ngày\n\nLưu ý:\nthuốc số 1: Có thể làm đường trong máu xuống quá thấp nếu bỏ bữa.\nthuốc số 2: Không dùng cho phụ nữ có thai. Báo bác sĩ nếu đau cơ hoặc vàng da.\nthuốc số 3: dễ buồn ngủ + không ngưng đột ngột + tránh rượu"
  },
  {
    "id": "Q023",
    "imageFile": "Q023.jpg",
    "gloss": "Dùng cho:\nthuốc số 1: bác sĩ kê thuốc + số 1 + Dùng cho người bị tiểu đường típ 2.\nthuốc số 2: bác sĩ kê thuốc + số 2 + Người bị tiểu đường típ 2 + Người cần giảm đường máu\nthuốc số 3: bác sĩ kê thuốc + số 3 + Người bị huyết áp cao + Người cần bác sĩ kê thuốc hạ huyết áp\nthuốc số 4: bác sĩ kê thuốc + số 4 + Dùng cho người bị mỡ máu cao.\n\nDùng như nào:\nthuốc số 1: uống + 3 viên + buổi sáng + mỗi ngày\nthuốc số 2: uống + 1 viên + buổi sáng + và + buổi tối + mỗi ngày\nthuốc số 3: uống + 1 viên + buổi sáng + mỗi ngày\nthuốc số 4: uống + 1 viên + buổi tối + mỗi ngày\n\nLưu ý:\nthuốc số 1: Có thể làm đường trong máu xuống quá thấp nếu bỏ bữa.\nthuốc số 2: Uống sau ăn + Theo dõi đường máu + Tránh rượu + Cẩn thận nếu bệnh thận\nthuốc số 3: Không dùng cho người mang thai + Uống đúng giờ mỗi ngày + Nếu khó thở hoặc sưng mặt, đi cấp cứu\nthuốc số 4: Không dùng cho phụ nữ có thai. Báo bác sĩ nếu đau cơ hoặc vàng da."
  },
  {
    "id": "Q024",
    "imageFile": "Q024.jpg",
    "gloss": "Dùng cho:\nthuốc số 1: bác sĩ kê thuốc + số 1 + Dùng cho người bị tiểu đường típ 2.\nthuốc số 2: bác sĩ kê thuốc + số 2 + Người bị tiểu đường típ 2 + Người cần giảm đường máu\nthuốc số 3: bác sĩ kê thuốc + số 3 + giảm + nguy cơ + cao huyết áp\nthuốc số 4: bác sĩ kê thuốc + số 4 + người bị cao huyết áp + người cần bảo vệ tim + người cần bảo vệ thận\n\nDùng như nào:\nthuốc số 1: uống + 2 viên + buổi sáng + mỗi ngày\nthuốc số 2: uống + 1 viên + buổi sáng + và + buổi tối + mỗi ngày\nthuốc số 3: uống + 1 viên + buổi sáng + mỗi ngày\nthuốc số 4: uống + 1 viên + buổi tối + mỗi ngày\n\nLưu ý:\nthuốc số 1: Có thể làm đường trong máu xuống quá thấp nếu bỏ bữa.\nthuốc số 2: Uống sau ăn + Theo dõi đường máu + Tránh rượu + Cẩn thận nếu bệnh thận\nthuốc số 3: uống + đều đặn + mỗi ngày + không + tự ý + ngừng thuốc\nthuốc số 4: không dùng cho người mang thai + uống đúng giờ + không tự ý ngừng"
  },
  {
    "id": "Q025",
    "imageFile": "Q025.jpg",
    "gloss": "Dùng cho:\nbác sĩ kê thuốc + số 1 + đau họng do vi khuẩn + đau tai do vi khuẩn + sốt do nhiễm khuẩn + viêm xoang + viêm phổi nhẹ theo đơn\n\nDùng như nào:\nuống + 1 viên + buổi sáng + và + buổi chiều + và + buổi tối + mỗi ngày\n\nLưu ý:\nuống đầu bữa ăn + uống đúng giờ + uống đủ đợt + không tự ngưng + đi khám nếu khó thở"
  },
  {
    "id": "Q026",
    "imageFile": "Q026.jpg",
    "gloss": "Dùng cho:\nthuốc số 1: bác sĩ kê thuốc + số 1 + đau họng do vi khuẩn + đau tai do vi khuẩn + sốt do nhiễm khuẩn + viêm xoang + viêm phổi nhẹ theo đơn\nthuốc số 2: bác sĩ kê thuốc + số 2 + Người bị viêm âm đạo do nấm hoặc vi khuẩn, theo đơn bác sĩ.\n\nDùng như nào:\nthuốc số 1: uống + 1 viên + buổi sáng + và + 1 viên + buổi tối + mỗi ngày\nthuốc số 2: uống + 1 viên + buổi tối + mỗi ngày\n\nLưu ý:\nthuốc số 1: uống đầu bữa ăn + uống đúng giờ + uống đủ đợt + không tự ngưng + đi khám nếu khó thở\nthuốc số 2: Chỉ đặt âm đạo. + Dùng đúng số ngày bác sĩ dặn. + Không dùng nếu bị dị ứng thuốc. + Đi khám nếu đau nhiều hoặc khó thở."
  },
  {
    "id": "Q027",
    "imageFile": "Q027.jpg",
    "gloss": "Dùng cho:\nthuốc số 1: bác sĩ kê thuốc + số 1 + giúp bạn + cảm thấy + dễ chịu hơn\nthuốc số 2: bác sĩ kê thuốc + số 2 + Bù nước + Bù muối + Hỗ trợ khi tiêu chảy + Hỗ trợ khi nôn\n\nDùng như nào:\nthuốc số 1: uống + 2 viên + buổi sáng + và + buổi chiều + mỗi ngày\nthuốc số 2: uống + mỗi ngày\n\nLưu ý:\nthuốc số 1: mỗi lần uống + cách nhau + 4-6 tiếng + không quá + 4 viên + mỗi ngày + uống nhiều + hại gan\nthuốc số 2: Pha đúng nước + Không pha sai + Theo dõi dấu mất nước + Đi khám khi nặng"
  },
  {
    "id": "Q028",
    "imageFile": "Q028.jpg",
    "gloss": "Dùng cho:\nthuốc số 1: bác sĩ kê thuốc + số 1 + dùng khi bị nhiễm khuẩn do vi khuẩn + dùng theo đơn bác sĩ\nthuốc số 2: bác sĩ kê thuốc + số 2 + giúp bạn + cảm thấy + dễ chịu hơn\n\nDùng như nào:\nthuốc số 1: uống + 1 viên + mỗi ngày\nthuốc số 2: uống + 1 viên + mỗi ngày\n\nLưu ý:\nthuốc số 1: uống đúng giờ + uống đủ số ngày + không tự ý ngừng thuốc + báo bác sĩ nếu nổi ban hoặc khó thở\nthuốc số 2: mỗi lần uống + cách nhau + 4-6 tiếng + không quá + 4 viên + mỗi ngày + uống nhiều + hại gan"
  },
  {
    "id": "Q029",
    "imageFile": "Q029.jpg",
    "gloss": "Dùng cho:\nbác sĩ kê thuốc + số 1 + đau họng do vi khuẩn + đau tai do vi khuẩn + sốt do nhiễm khuẩn + viêm xoang + viêm phổi nhẹ theo đơn\n\nDùng như nào:\nuống + 1 viên + mỗi ngày\n\nLưu ý:\nuống đầu bữa ăn + uống đúng giờ + uống đủ đợt + không tự ngưng + đi khám nếu khó thở"
  },
  {
    "id": "Q030",
    "imageFile": "Q030.jpg",
    "gloss": "Dùng cho:\nthuốc số 1: bác sĩ kê thuốc + số 1 + Người bị huyết áp cao + Người cần bác sĩ kê thuốc hạ huyết áp\nthuốc số 2: bác sĩ kê thuốc + số 2 + Dùng cho người bị mỡ máu cao.\n\nDùng như nào:\nthuốc số 1: uống + 1 viên + buổi sáng + mỗi ngày\nthuốc số 2: uống + 1 viên + buổi tối + mỗi ngày\n\nLưu ý:\nthuốc số 1: Không dùng cho người mang thai + Uống đúng giờ mỗi ngày + Nếu khó thở hoặc sưng mặt, đi cấp cứu\nthuốc số 2: Không dùng cho phụ nữ có thai. Báo bác sĩ nếu đau cơ hoặc vàng da."
  }
];

function createVslGlossSurvey() {
  if (IMAGE_FOLDER_ID === 'PASTE_GOOGLE_DRIVE_IMAGE_FOLDER_ID_HERE') {
    throw new Error('Paste your Google Drive image folder ID into IMAGE_FOLDER_ID first.');
  }

  const folder = DriveApp.getFolderById(IMAGE_FOLDER_ID);
  const form = FormApp.create(FORM_TITLE);
  form.setDescription(
    'Please evaluate each generated Vietnamese Sign Language gloss from the prescription image. ' +
    'Do not enter personal information. Only enter your respondent code.'
  );
  form.setConfirmationMessage('Thank you for completing the VSL gloss evaluation.');

  form.addTextItem()
    .setTitle('Respondent code')
    .setHelpText('Enter only the assigned respondent code. Do not enter your name, email, phone number, or address.')
    .setRequired(true);

  QUESTIONS.forEach((question, index) => {
    form.addPageBreakItem().setTitle(question.id);

    const imageFile = getFileByName_(folder, question.imageFile);
    form.addImageItem()
      .setTitle(question.id + ' prescription image')
      .setImage(imageFile.getBlob())
      .setWidth(650);

    form.addSectionHeaderItem()
      .setTitle('Generated gloss')
      .setHelpText(question.gloss);

    form.addScaleItem()
      .setTitle(question.id + ' score')
      .setHelpText('Evaluate gloss quality. 1 = not acceptable / seriously wrong / unsafe. 5 = very good / usable.')
      .setBounds(1, 5)
      .setLabels('1 = not acceptable', '5 = very good')
      .setRequired(true);

    form.addParagraphTextItem()
      .setTitle(question.id + ' optional comment')
      .setHelpText('Optional: suggest corrections or explain the score.')
      .setRequired(false);
  });

  Logger.log('Edit URL: ' + form.getEditUrl());
  Logger.log('Live URL: ' + form.getPublishedUrl());
}

function getFileByName_(folder, fileName) {
  const files = folder.getFilesByName(fileName);
  if (!files.hasNext()) {
    throw new Error('Missing image in Drive folder: ' + fileName);
  }
  return files.next();
}
