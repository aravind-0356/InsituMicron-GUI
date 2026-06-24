# gui_analysis.py
import os
import csv
import time
import numpy as np
import pyqtgraph as pg

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QFileDialog, QGroupBox, QFormLayout, QLineEdit, QMessageBox, QSplitter,
    QSizePolicy, QTextEdit
)
from PySide6.QtCore import Qt, Signal, Slot
from PySide6.QtGui import QDoubleValidator

from constants import PRIMARY_COLOR, ACCENT_COLOR
from execution.material_analysis import MaterialAnalysisEngine
from execution.pdf_reporter import PDFReporter
import pyqtgraph.exporters

from logging_config import get_logger
logger = get_logger(__name__)

from gui_panels import setup_plot_style

class AnalysisReportingPanel(QWidget):
    def __init__(self):
        super().__init__()
        self.engine = MaterialAnalysisEngine()
        self.current_data = None  # Tuple (load, disp)
        self.analysis_result = None
        self.init_ui()

    def init_ui(self):
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(15, 15, 15, 15)
        main_layout.setSpacing(15)

        # Top Bar: File selection
        top_bar = QHBoxLayout()
        self.btn_load_csv = QPushButton("Load Test Data (CSV)")
        self.btn_load_csv.setMinimumHeight(40)
        self.btn_load_csv.setStyleSheet(
            f"QPushButton {{ background-color: {PRIMARY_COLOR}; color: white; font-weight: bold; padding: 0 20px; font-size: 16px; }}"
            f"QPushButton:hover {{ background-color: {ACCENT_COLOR}; }}"
        )
        self.lbl_loaded_file = QLabel("No file loaded")
        self.lbl_loaded_file.setStyleSheet("color: #7f8c8d; font-style: italic; font-size: 16px;")
        
        top_bar.addWidget(self.btn_load_csv)
        top_bar.addWidget(self.lbl_loaded_file)
        top_bar.addStretch()
        main_layout.addLayout(top_bar)

        # Splitter for Controls and Graph
        splitter = QSplitter(Qt.Horizontal)
        
        # Left Panel: Parameters & Results
        left_panel = QWidget()
        left_layout = QVBoxLayout(left_panel)
        left_layout.setContentsMargins(0, 0, 0, 0)
        left_layout.setSpacing(15)

        # Dimensions Group
        grp_dims = QGroupBox("Specimen Dimensions")
        dim_form = QFormLayout(grp_dims)
        dim_form.setSpacing(10)

        self.inp_area = QLineEdit("37.5")
        self.inp_area.setValidator(QDoubleValidator())
        self.inp_gauge = QLineEdit("50.0")
        self.inp_gauge.setValidator(QDoubleValidator())

        dim_form.addRow("Area (mm²):", self.inp_area)
        dim_form.addRow("Gauge Length (mm):", self.inp_gauge)
        left_layout.addWidget(grp_dims)

        # Action Buttons
        self.btn_analyze = QPushButton("Run Analysis")
        self.btn_analyze.setMinimumHeight(45)
        self.btn_analyze.setStyleSheet(
            f"QPushButton {{ background-color: {ACCENT_COLOR}; color: white; font-weight: bold; font-size: 16px; }}"
            f"QPushButton:hover {{ background-color: {PRIMARY_COLOR}; }}"
        )
        left_layout.addWidget(self.btn_analyze)

        self.btn_report = QPushButton("Generate PDF Report")
        self.btn_report.setMinimumHeight(45)
        self.btn_report.setStyleSheet(
            "QPushButton { background-color: #27ae60; color: white; font-weight: bold; font-size: 16px; }"
            "QPushButton:hover { background-color: #2ecc71; }"
            "QPushButton:disabled { background-color: #bdc3c7; }"
        )
        self.btn_report.setEnabled(False)
        left_layout.addWidget(self.btn_report)

        # Results Group
        grp_results = QGroupBox("Mechanical Properties")
        res_form = QFormLayout(grp_results)
        res_form.setSpacing(12)
        
        lbl_style = "font-size: 18px; font-weight: bold; color: #2c3e50;"
        val_style = f"font-size: 18px; font-weight: bold; color: {PRIMARY_COLOR};"

        self.lbl_e = QLabel("--")
        self.lbl_e.setStyleSheet(val_style)
        self.lbl_ys = QLabel("--")
        self.lbl_ys.setStyleSheet(val_style)
        self.lbl_uts = QLabel("--")
        self.lbl_uts.setStyleSheet(val_style)
        self.lbl_break = QLabel("--")
        self.lbl_break.setStyleSheet(val_style)

        res_form.addRow(QLabel("Young's Modulus:"), self.lbl_e)
        res_form.addRow(QLabel("Yield Strength:"), self.lbl_ys)
        res_form.addRow(QLabel("UTS:"), self.lbl_uts)
        res_form.addRow(QLabel("Break Stress:"), self.lbl_break)
        lbl_hint = QLabel("Note: Drag the blue shaded region on the\nchart to manually override the elastic range.")
        lbl_hint.setStyleSheet("color: #7f8c8d; font-style: italic; font-size: 14px;")
        left_layout.addWidget(lbl_hint)

        left_layout.addWidget(grp_results)

        # Operator Comments Group
        grp_comments = QGroupBox("Operator Notes")
        com_layout = QVBoxLayout(grp_comments)
        com_layout.setSpacing(5)
        
        self.txt_comments = QTextEdit()
        self.txt_comments.setPlaceholderText("Enter any test notes or operator comments here...")
        self.txt_comments.setMaximumHeight(80)
        
        self.btn_save_notes = QPushButton("Save Notes")
        self.btn_save_notes.setMinimumHeight(45)
        self.btn_save_notes.setStyleSheet(
            f"QPushButton {{ background-color: {PRIMARY_COLOR}; color: white; font-weight: bold; font-size: 14px; padding: 5px; }}"
            f"QPushButton:hover {{ background-color: {ACCENT_COLOR}; }}"
        )
        self.btn_save_notes.clicked.connect(self.save_notes)
        
        com_layout.addWidget(self.txt_comments)
        com_layout.addWidget(self.btn_save_notes)
        left_layout.addWidget(grp_comments)
        
        left_layout.addStretch()
        splitter.addWidget(left_panel)

        # Right Panel: Plot
        right_panel = QWidget()
        right_layout = QVBoxLayout(right_panel)
        right_layout.setContentsMargins(0, 0, 0, 0)
        
        self.plot_widget = pg.PlotWidget()
        setup_plot_style(self.plot_widget, "Stress-Strain Analysis", "Strain (mm/mm)", "Stress (MPa)")
        
        self.plot_widget.addLegend(labelTextSize='12pt')
        
        # Plot curves
        self.curve_main = self.plot_widget.plot(pen=pg.mkPen(color='#2c3e50', width=3), name="Stress-Strain")
        self.curve_modulus = self.plot_widget.plot(pen=pg.mkPen(color='#2980b9', width=2, style=Qt.DashLine), name="Modulus Fit")
        self.curve_offset = self.plot_widget.plot(pen=pg.mkPen(color='#8e44ad', width=2, style=Qt.DotLine), name="0.2% Offset")
        
        # Key event markers
        self.curve_yield = self.plot_widget.plot(pen=None, symbol='o', symbolSize=14, symbolBrush='#8e44ad', name="Yield Point")
        self.curve_uts = self.plot_widget.plot(pen=None, symbol='t', symbolSize=16, symbolBrush='#e74c3c', name="UTS")
        self.curve_break = self.plot_widget.plot(pen=None, symbol='x', symbolSize=16, symbolBrush='#e67e22', name="Break")
        
        # Interactive region for elastic modulus calculation
        self.elastic_region = pg.LinearRegionItem(brush=pg.mkBrush(41, 128, 185, 50))
        self.elastic_region.setZValue(-10)
        self.plot_widget.addItem(self.elastic_region)
        self.elastic_region.hide()
        
        # Hook up region change to re-calc
        self.elastic_region.sigRegionChangeFinished.connect(self.on_region_changed)

        right_layout.addWidget(self.plot_widget)
        splitter.addWidget(right_panel)
        
        # Splitter sizing
        splitter.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        splitter.setSizes([350, 850])
        main_layout.addWidget(splitter, 1)

        # Connections
        self.btn_load_csv.clicked.connect(self.load_csv)
        self.btn_analyze.clicked.connect(self.run_analysis)
        self.btn_report.clicked.connect(self.generate_report)

    def load_csv(self):
        filepath, _ = QFileDialog.getOpenFileName(self, "Open Test Data", "", "CSV Files (*.csv);;All Files (*)")
        if not filepath:
            return

        try:
            load_data = []
            disp_data = []
            
            with open(filepath, 'r', encoding='utf-8') as f:
                reader = csv.DictReader(f)
                if reader.fieldnames is None:
                    raise ValueError("CSV file is empty or missing headers")
                headers = [h.strip() for h in reader.fieldnames]
                
                # Try to find load and disp columns
                load_col = next((h for h in headers if 'load' in h.lower() and 'uni' in h.lower()), None)
                if not load_col:
                    load_col = next((h for h in headers if 'load' in h.lower()), None)
                    
                disp_col = next((h for h in headers if 'disp' in h.lower() and 'uni' in h.lower()), None)
                if not disp_col:
                    disp_col = next((h for h in headers if 'disp' in h.lower()), None)
                
                if not load_col or not disp_col:
                    QMessageBox.warning(self, "Column Error", "Could not automatically identify Load and Displacement columns.")
                    return

                for row in reader:
                    try:
                        load_data.append(float(row[load_col]))
                        disp_data.append(float(row[disp_col]))
                    except (ValueError, TypeError):
                        pass

            if not load_data:
                QMessageBox.warning(self, "Data Error", "No valid numeric data found in selected columns.")
                return

            self.current_data = (np.array(load_data), np.array(disp_data))
            self.lbl_loaded_file.setText(os.path.basename(filepath))
            
            # Auto-run analysis when data is loaded
            self.run_analysis()
            
        except Exception as e:
            logger.error(f"Error loading CSV for analysis: {e}")
            QMessageBox.critical(self, "File Error", f"Failed to load file: {e}")

    def run_analysis(self):
        if self.current_data is None:
            QMessageBox.warning(self, "No Data", "Please load a test data CSV first.")
            return

        try:
            area = float(self.inp_area.text())
            gauge = float(self.inp_gauge.text())
            if area <= 0 or gauge <= 0:
                raise ValueError("Dimensions must be positive.")
        except ValueError:
            QMessageBox.warning(self, "Input Error", "Please enter valid positive numbers for dimensions.")
            return

        load, disp = self.current_data
        
        # Check if region is active and user has adjusted it manually
        override_range = None
        if self.elastic_region.isVisible():
            r_min, r_max = self.elastic_region.getRegion()
            override_range = (r_min, r_max)

        # Run the engine
        try:
            self.analysis_result = self.engine.analyse(
                load.tolist(), disp.tolist(), area, gauge,
                manual_elastic_range=override_range
            )
            self.update_ui_results()
        except Exception as e:
            logger.error(f"Analysis engine error: {e}")
            QMessageBox.critical(self, "Analysis Error", f"Failed to run analysis:\n{str(e)}")

    def update_ui_results(self):
        res = self.analysis_result
        if not res:
            return

        # Update labels
        self.lbl_e.setText(f"{res.youngs_modulus:,.1f} MPa" if res.youngs_modulus > 0 else "--")
        self.lbl_ys.setText(f"{res.yield_stress:,.2f} MPa" if res.yield_stress is not None else "--")
        self.lbl_uts.setText(f"{res.uts_stress:,.2f} MPa" if res.uts_stress is not None else "--")
        self.lbl_break.setText(f"{res.break_stress:,.2f} MPa" if res.break_stress is not None else "--")

        self.btn_report.setEnabled(True)

        # Update plot
        strain = np.array(res.strain)
        stress = np.array(res.stress)
        
        self.curve_main.setData(strain, stress)
        
        if res.modulus_line:
            self.curve_modulus.setData(res.modulus_line[0], res.modulus_line[1])
        else:
            self.curve_modulus.setData([], [])
            
        if res.offset_line:
            self.curve_offset.setData(res.offset_line[0], res.offset_line[1])
        else:
            self.curve_offset.setData([], [])

        # Update points (Yield, UTS, Break)
        if res.yield_stress is not None:
            self.curve_yield.setData([res.yield_strain], [res.yield_stress])
        else:
            self.curve_yield.setData([], [])
            
        if res.uts_stress is not None:
            self.curve_uts.setData([res.uts_strain], [res.uts_stress])
        else:
            self.curve_uts.setData([], [])
            
        if res.break_stress is not None:
            self.curve_break.setData([res.break_strain], [res.break_stress])
        else:
            self.curve_break.setData([], [])

        # Update elastic region bounds
        if not self.elastic_region.isVisible():
            self.elastic_region.show()
            # block signals so we don't trigger re-calc recursively
            self.elastic_region.blockSignals(True)
            start_idx = max(0, min(res.elastic_start_idx, len(strain) - 1))
            end_idx = max(0, min(res.elastic_end_idx, len(strain) - 1))
            self.elastic_region.setRegion([strain[start_idx], strain[end_idx]])
            self.elastic_region.blockSignals(False)

        # Auto-range plot to fit the main curve, not the extrapolated modulus line
        self.plot_widget.autoRange()

        # Show warnings
        if res.warnings:
            warn_text = "\n".join(f"• {w}" for w in res.warnings)
            QMessageBox.information(self, "Analysis Warnings", f"The analysis completed with some warnings:\n\n{warn_text}")

    def on_region_changed(self):
        """When user manually drags the elastic region, re-run analysis."""
        if self.current_data:
            self.run_analysis()

    def save_notes(self):
        """Acknowledge notes saved for the user."""
        QMessageBox.information(self, "Notes Saved", "Operator notes have been saved for the report.")

    def generate_report(self):
        if not self.analysis_result:
            QMessageBox.warning(self, "No Data", "Please run analysis before generating a report.")
            return

        save_path, _ = QFileDialog.getSaveFileName(self, "Save PDF Report", "Material_Test_Report.pdf", "PDF Files (*.pdf)")
        if not save_path:
            return

        if not save_path.lower().endswith('.pdf'):
            save_path += '.pdf'

        # 1. Capture pyqtgraph plot to temporary image
        temp_img_path = os.path.join(os.path.dirname(save_path), "temp_plot_export.png")
        try:
            exporter = pyqtgraph.exporters.ImageExporter(self.plot_widget.plotItem)
            exporter.export(temp_img_path)
        except Exception as e:
            logger.error("Failed to export plot image: %s", e)
            QMessageBox.critical(self, "Export Error", f"Failed to capture graph image:\n{e}")
            return

        # 2. Gather data
        filename = self.lbl_loaded_file.text()
        area = self.inp_area.text()
        gauge = self.inp_gauge.text()
        comments = self.txt_comments.toPlainText()

        res = self.analysis_result
        metadata = {
            'filename': filename,
            'area': area,
            'gauge_length': gauge,
            'date': time.strftime("%Y-%m-%d %H:%M:%S")
        }
        
        # Try to pull sample parameters from main window if available
        mw = self.window()
        if hasattr(mw, '_sample_id'):
            metadata['sample_id'] = getattr(mw, '_sample_id', '--')
            metadata['sample_type'] = getattr(mw, '_sample_type', '--')
            metadata['width'] = getattr(mw, '_width', '--')
            metadata['thickness'] = getattr(mw, '_thickness', '--')
            metadata['radius'] = getattr(mw, '_radius', '--')
        
        results = {
            'e_modulus': f"{res.youngs_modulus:,.1f}" if res.youngs_modulus > 0 else "--",
            'yield_strength': f"{res.yield_stress:,.2f}" if res.yield_stress is not None else "--",
            'uts': f"{res.uts_stress:,.2f}" if res.uts_stress is not None else "--",
            'break_stress': f"{res.break_stress:,.2f}" if res.break_stress is not None else "--"
        }

        # 3. Generate PDF
        reporter = PDFReporter()
        try:
            reporter.generate_report(save_path, metadata, results, comments, temp_img_path)
            
            # Ask if they want to open it
            msg = QMessageBox(self)
            msg.setWindowTitle("Success")
            msg.setText(f"Report successfully generated at:\n{save_path}")
            open_btn = msg.addButton("Open Report", QMessageBox.ActionRole)
            msg.addButton(QMessageBox.Ok)
            msg.exec()
            
            if msg.clickedButton() == open_btn:
                os.startfile(os.path.normpath(save_path))
                
        except Exception as e:
            QMessageBox.critical(self, "Report Error", f"Failed to generate PDF report:\n{e}")
        finally:
            # Clean up temp image
            if os.path.exists(temp_img_path):
                try:
                    os.remove(temp_img_path)
                except:
                    pass
