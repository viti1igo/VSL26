const EXISTING_FORM_ID = 'PASTE_EXISTING_FORM_ID_HERE';

function updateExistingVslFormBilingual() {
  const form = FormApp.openById(EXISTING_FORM_ID);

  form.setTitle('VSL Prescription Gloss Expert Evaluation / Đánh giá gloss VSL cho đơn thuốc');
  form.setDescription(
    'English: Please evaluate each generated Vietnamese Sign Language gloss from the prescription image. Do not enter personal information. Only enter your respondent code.\n\n' +
    'Tiếng Việt: Vui lòng đánh giá gloss Ngôn ngữ ký hiệu Việt Nam được tạo từ hình ảnh đơn thuốc. Không nhập thông tin cá nhân. Chỉ nhập mã số người trả lời.'
  );
  form.setConfirmationMessage(
    'Thank you for completing the VSL gloss evaluation. / Cảm ơn bạn đã hoàn thành đánh giá gloss VSL.'
  );

  const items = form.getItems();
  items.forEach((item) => {
    const title = item.getTitle() || '';

    if (item.getType() === FormApp.ItemType.TEXT && title === 'Respondent code') {
      item.asTextItem()
        .setTitle('Respondent code / Mã số người trả lời')
        .setHelpText(
          'English: Enter only the assigned respondent code. Do not enter your name, email, phone number, or address.\n' +
          'Tiếng Việt: Chỉ nhập mã số được cung cấp. Không nhập tên, email, số điện thoại, hoặc địa chỉ.'
        );
      return;
    }

    if (item.getType() === FormApp.ItemType.IMAGE && title.match(/^Q\d{3} prescription image$/)) {
      const qid = title.match(/^(Q\d{3})/)[1];
      item.asImageItem().setTitle(qid + ' prescription image / Hình ảnh đơn thuốc');
      return;
    }

    if (item.getType() === FormApp.ItemType.SECTION_HEADER && title === 'Generated gloss') {
      item.asSectionHeaderItem().setTitle('Generated gloss / Gloss được tạo');
      return;
    }

    if (item.getType() === FormApp.ItemType.SCALE && title.match(/^Q\d{3} score$/)) {
      const qid = title.match(/^(Q\d{3})/)[1];
      item.asScaleItem()
        .setTitle(qid + ' score / Điểm đánh giá')
        .setHelpText(
          'English: Evaluate gloss quality. 1 = not acceptable / seriously wrong / unsafe. 5 = very good / usable.\n' +
          'Tiếng Việt: Đánh giá chất lượng gloss. 1 = không đạt / sai nghiêm trọng / không an toàn. 5 = rất tốt / có thể sử dụng.'
        )
        .setLabels('1 = not acceptable / không đạt', '5 = very good / rất tốt');
      return;
    }

    if (item.getType() === FormApp.ItemType.PARAGRAPH_TEXT && title.match(/^Q\d{3} optional comment$/)) {
      const qid = title.match(/^(Q\d{3})/)[1];
      item.asParagraphTextItem()
        .setTitle(qid + ' optional comment / Góp ý thêm nếu có')
        .setHelpText(
          'English: Optional: suggest corrections or explain the score.\n' +
          'Tiếng Việt: Không bắt buộc: góp ý chỉnh sửa gloss hoặc giải thích điểm đánh giá.'
        );
    }
  });

  Logger.log('Updated existing bilingual form.');
  Logger.log('Edit URL: ' + form.getEditUrl());
  Logger.log('Live URL: ' + form.getPublishedUrl());
}
