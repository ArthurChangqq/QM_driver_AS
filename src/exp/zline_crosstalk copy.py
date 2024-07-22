from qm.QuantumMachinesManager import QuantumMachinesManager
from qm.qua import *
from qualang_tools.loops import from_array
from exp.RO_macros import multiRO_declare, multiRO_measurement, multiRO_pre_save
import warnings
warnings.filterwarnings("ignore")
import exp.config_par as gc
from qualang_tools.units import unit
u = unit(coerce_to_integer=True)
import xarray as xr
import numpy as np
from exp.QMMeasurement import QMMeasurement

warnings.filterwarnings("ignore")
from qualang_tools.units import unit
u = unit(coerce_to_integer=True)
from exp.config_par import get_offset

class FluxCrosstalk( QMMeasurement ):

    """
    Parameters:
    measure flux crosstalk with the given Z flux(voltage) range.\n

    expect_crosstalk:\n
    no unit.\n

    flux_modify_range:\n
    unit in V.\n

    z_time:\n
    unit in micro second.\n

    measure_method:\n
    ramsey or long drive.\n
    see https://docs.google.com/presentation/d/18QqU46g3KktW5dPgIXpiLrI3leNX1FnE/edit?usp=drive_link&ouid=115212552955966668572&rtpof=true&sd=true\n
    page 2\n

    z_method:\n
    pulse or offset.\n
    The offset mode does not apply corrections from the crosstalk matrix.\n
    Only pulse mode does.\n
    2024/07/22\n

    ro_elements: ["q0_ro"], temporarily support only 1 element in the list.\n
    who do ramsey.\n
    zz_source_xy: ["q1_xy"], temporarily support only 1 element in the list.\n
    who is applied X or I to measure ZZ (not Z line) crosstalk is.\n
    coupler_z: ["q2_z"], temporarily support only 1 element in the list.\n
    the coupler between target_element and crosstalk_element, whose frequency is tuned to find ZZ free point. \n
    Return: \n

    detector_qubit:\n
    who readout.\n

    detector_is_coupler:\n
    If detector is coupler, readout is not so easy.\n
    I haven't do this.\n

    flux_crosstalk_source_qubit:\n
    Who provide its z_line to make flux crosstalk to others.\n 
    """

    def __init__( self, config, qmm: QuantumMachinesManager ):
        super().__init__( config, qmm )

        self.expect_crosstalk = 0.01
        self.flux_modify_range = 0.2
        self.z_time = 1

        self.measure_method = "ramsey"   #long_drive
        self.z_method = "pulse"     #offset

        self.detector_qubit = ["q3"]
        self.detector_is_coupler = "False"
        self.flux_crosstalk_source_qubit = ["q4"]

    def _get_qua_program( self ):
        self.flux_qua = self._lin_flux_array( )
        self.evo_time_tick_qua = self._evo_time_tick_array( )
        with program() as ZZfree:
            iqdata_stream = multiRO_declare( self.ro_elements[0] )
            n = declare(int)
            n_st = declare_stream()

            t = declare(int)  # QUA variable for the idle time, unit in clock cycle
            dc = declare(fixed) 

            with for_(n, 0, n < self.shot_num, n + 1):  # QUA for_ loop for averaging
                with for_(*from_array(dc, self.flux_qua)):
                    with for_( *from_array(t, self.evo_time_tick_qua) ):
                        # Initialization
                        # Wait for the resonator to deplete
                        if self.initializer is None:
                            wait(10 * u.us, self.ro_elements[0])
                        else:
                            try:
                                self.initializer[0](*self.initializer[1])
                            except:
                                print("initializer didn't work!")
                                wait(1 * u.us, self.ro_elements[0]) 

                        play("x90", self.zz_detector_xy[0])  # 1st x90 gate
                        wait(5)
                        align()
                        play("const"*amp(dc*2.), self.coupler_z[0], t)    # const 預設0.5
                        align()
                        play("x180", self.zz_detector_xy[0])     #flip
                        play("x180", self.zz_source_xy[0])      #make ZZ crosstalk
                        wait(5)
                        align()

                        play("const"*amp(dc*2.), self.coupler_z[0], t)    # const 預設0.5
                        align()
                        # wait(5)
                        # frame_rotation_2pi(0.5, self.zz_detector_xy[0])  # Virtual Z-rotation
                        play("-x90", self.zz_detector_xy[0])  # 2nd x90 gate
                        align()
                        
                        # Readout
                        multiRO_measurement( iqdata_stream, self.ro_elements[0], weights="rotated_") 
                # Save the averaging iteration to get the progress bar
                save(n, n_st)

            with stream_processing():
                # Cast the data into a 1D vector, average the 1D vectors together and store the results on the OPX processor
                multiRO_pre_save( iqdata_stream, self.ro_elements[0], (len(self.flux_qua), len(self.evo_time_tick_qua)))
                n_st.save("iteration")

        return ZZfree

    def _get_fetch_data_list( self ):
        ro_ch_name = []
        for r_name in self.ro_elements:
            ro_ch_name.append(f"{r_name}_I")
            ro_ch_name.append(f"{r_name}_Q")

        data_list = ro_ch_name + ["iteration"]   
        return data_list
     
    def _data_formation( self ):
        output_data = {}

        for r_idx, r_name in enumerate(self.ro_elements):
            output_data[r_name] = ( ["mixer","flux","time"],
                                np.array([self.fetch_data[r_idx*2], self.fetch_data[r_idx*2+1]]) )
        dataset = xr.Dataset(
            output_data,
            coords={"mixer":np.array(["I","Q"]), "flux": self.flux_qua, "time": 4*self.evo_time_tick_qua}
        )

        self._attribute_config()
        dataset.attrs["ro_LO"] = self.ref_ro_LO
        dataset.attrs["ro_IF"] = self.ref_ro_IF
        dataset.attrs["xy_LO"] = self.ref_xy_LO
        dataset.attrs["xy_IF"] = self.ref_xy_IF
        dataset.attrs["z_offset"] = self.z_offset

        dataset.attrs["z_amp_const"] = self.z_amp
        return dataset
    
    def _attribute_config( self ):
        self.ref_ro_IF = []
        self.ref_ro_LO = []
        for r in self.ro_elements:
            self.ref_ro_IF.append(gc.get_IF(r, self.config))
            self.ref_ro_LO.append(gc.get_LO(r, self.config))

        self.ref_xy_IF = []
        self.ref_xy_LO = []
        for xy in self.zz_detector_xy:
            self.ref_xy_IF.append(gc.get_IF(xy, self.config))
            self.ref_xy_LO.append(gc.get_LO(xy, self.config))
        for xy in self.zz_source_xy:
            self.ref_xy_IF.append(gc.get_IF(xy, self.config))
            self.ref_xy_LO.append(gc.get_LO(xy, self.config))

        self.z_offset = []
        self.z_amp = []
        for z in self.coupler_z:
            self.z_offset.append( gc.get_offset(z, self.config ))
            self.z_amp.append(gc.get_const_wf(z, self.config ))
     
    def _lin_flux_array( self ):
        return np.arange( self.flux_range[0], self.flux_range[1], self.resolution )
    
    def _evo_time_tick_array( self ):
        point_per_period = 20
        Ramsey_period = (1e3/self.predict_detune)* u.ns
        tick_resolution = (Ramsey_period//(4*point_per_period))
        evo_time_tick_max = tick_resolution *point_per_period*6
        evo_time_tick = np.arange( 4, evo_time_tick_max, tick_resolution)
        return evo_time_tick

def ramsey_z_offset( flux_modify_range, prob_q_name:str, ro_element:str, z_line:list, config, qmm:QuantumMachinesManager, evo_time=1, expect_crosstalk:float=1.0, n_avg:int=100, initializer:tuple=None, simulate=True):
    """
    Mapping z offset crosstalk by qubit frequency 
    """
    a_min = -flux_modify_range
    a_max = flux_modify_range
    da = flux_modify_range/25

    flux_crosstalk = np.arange(a_min, a_max + da / 2, da)  # + da/2 to add a_max to amplitudes
    flux_target = np.arange(a_min, a_max - da / 2, da)*expect_crosstalk 
    evo_cc = (evo_time/4)*u.us
    # flux_target = np.arange(a_min*expect_crosstalk , (a_max + da / 2)*expect_crosstalk , da*expect_crosstalk/2 )#flux_crosstalk*expect_crosstalk 
    flux_target_len = len(flux_target) 
    flux_crosstalk_len = len(flux_crosstalk) 

    with program() as zc:
        iqdata_stream = multiRO_declare( ro_element )
        n = declare(int) 
        n_st = declare_stream()
        dc_1 = declare(fixed) 
        dc_2 = declare(fixed) 

        with for_(n, 0, n < n_avg, n + 1):
            
            with for_(*from_array(dc_1, flux_target)):
                
                with for_(*from_array(dc_2, flux_crosstalk)):

                    
                    # Init
                    if initializer is None:
                        wait(100*u.us)
                        #wait(thermalization_time * u.ns)
                    else:
                        try:
                            initializer[0](*initializer[1])
                        except:
                            print("Initializer didn't work!")
                            wait(100*u.us)

                    # Opration
                    play( "x90", prob_q_name )
                    align()
                    wait(25) 
                    set_dc_offset( z_line[0], "single", get_offset(z_line[0],config)+dc_1 )
                    set_dc_offset( z_line[1], "single", get_offset(z_line[1],config)+dc_2 )
                    align()
                    wait(evo_cc) 
                    set_dc_offset( z_line[0], "single", get_offset(z_line[0],config) )
                    set_dc_offset( z_line[1], "single", get_offset(z_line[1],config) )
                    align()
                    wait(25) 
                    play( "x90", prob_q_name )
                    wait(10) 

                    # Readout
                    align()
                    multiRO_measurement(iqdata_stream, ro_element, weights="rotated_")
            save(n, n_st)
        with stream_processing():
            n_st.save("iteration")
            multiRO_pre_save( iqdata_stream, ro_element, (flux_target_len,flux_crosstalk_len) )
    
    if simulate:
        simulation_config = SimulationConfig(duration=10_000)  # In clock cycles = 4ns
        job = qmm.simulate(config, zc, simulation_config)
        job.get_simulated_samples().con1.plot()
        plt.show()
    else:
        qm = qmm.open_qm(config)
        job = qm.execute(zc)

        ro_ch_name = []
        ro_ch_name.append(f"{ro_element}_I")
        ro_ch_name.append(f"{ro_element}_Q")
        data_list = ro_ch_name + ["iteration"]   
        results = fetching_tool(job, data_list=data_list, mode="live")

        fig, ax = plt.subplots(2)
        interrupt_on_close(fig, job)
        # fig.colorbar( p_i, ax=ax[0] )
        # fig.colorbar( p_q, ax=ax[1] )


        output_data = {}
        while results.is_processing():
            fetch_data = results.fetch_all()
            plt.cla()
            ax[0].cla()
            ax[1].cla()
            output_data[ro_element] = np.array([fetch_data[0], fetch_data[1]])
            plot_crosstalk_3Dscalar( flux_crosstalk, flux_target, output_data[ro_element][0], z_line, ax[0])
            plot_crosstalk_3Dscalar( flux_crosstalk, flux_target, output_data[ro_element][1], z_line, ax[1])
            iteration = fetch_data[-1]
            # Progress bar
            progress_counter(iteration, n_avg, start_time=results.get_start_time())      

            plt.tight_layout()
            plt.pause(1) 

        qm.close()
        return output_data, flux_target, flux_crosstalk

def ramsey_z_pulse( flux_modify_range, prob_q_name:str, ro_element:str, z_line:list, config, qmm:QuantumMachinesManager, evo_time=1, expect_crosstalk:float=1.0, n_avg:int=100, initializer:tuple=None, simulate=True):
    """
    Mapping z offset crosstalk by qubit frequency 
    """
    a_min = -flux_modify_range
    a_max = flux_modify_range
    da = flux_modify_range/100

    flux_crosstalk = np.arange(a_min, a_max + da / 2, da)  # + da/2 to add a_max to amplitudes
    flux_target = np.arange(a_min, a_max - da / 2, da)*expect_crosstalk 
    evo_cc = (evo_time/4)*u.us
    # flux_target = np.arange(a_min*expect_crosstalk , (a_max + da / 2)*expect_crosstalk , da*expect_crosstalk/2 )#flux_crosstalk*expect_crosstalk 
    flux_target_len = len(flux_target) 
    flux_crosstalk_len = len(flux_crosstalk) 

    with program() as zc:
        iqdata_stream = multiRO_declare( ro_element )
        n = declare(int) 
        n_st = declare_stream()
        dc_1 = declare(fixed) 
        dc_2 = declare(fixed) 

        with for_(n, 0, n < n_avg, n + 1):
            
            with for_(*from_array(dc_1, flux_target)):
                
                with for_(*from_array(dc_2, flux_crosstalk)):

                    
                    # Init
                    if initializer is None:
                        wait(100*u.us)
                        #wait(thermalization_time * u.ns)
                    else:
                        try:
                            initializer[0](*initializer[1])
                        except:
                            print("Initializer didn't work!")
                            wait(100*u.us)

                    # Opration
                    play( "x90", prob_q_name )
                    align()
                    wait(25)
                    # set_dc_offset( z_line[0], "single", get_offset(z_line[0],config))
                    # set_dc_offset( z_line[1], "single", get_offset(z_line[1],config))
                    # align()
                    play("const"*amp(dc_1*2.), z_line[0], evo_cc)         #const 預設0.5
                    play("const"*amp(dc_2*2.), z_line[1], evo_cc)
                    align()
                    wait(25) 
                    play( "x90", prob_q_name )
                    wait(10) 

                    # Readout
                    align()
                    multiRO_measurement(iqdata_stream, ro_element, weights="rotated_")
            save(n, n_st)
        with stream_processing():
            n_st.save("iteration")
            multiRO_pre_save( iqdata_stream, ro_element, (flux_target_len,flux_crosstalk_len) )
    
    if simulate:
        simulation_config = SimulationConfig(duration=10_000)  # In clock cycles = 4ns
        job = qmm.simulate(config, zc, simulation_config)
        job.get_simulated_samples().con2.plot()
        plt.show()
    else:
        qm = qmm.open_qm(config)
        job = qm.execute(zc)

        ro_ch_name = []
        ro_ch_name.append(f"{ro_element}_I")
        ro_ch_name.append(f"{ro_element}_Q")
        data_list = ro_ch_name + ["iteration"]   
        results = fetching_tool(job, data_list=data_list, mode="live")

        fig, ax = plt.subplots(2)
        interrupt_on_close(fig, job)
        # fig.colorbar( p_i, ax=ax[0] )
        # fig.colorbar( p_q, ax=ax[1] )


        output_data = {}
        while results.is_processing():
            fetch_data = results.fetch_all()
            plt.cla()
            ax[0].cla()
            ax[1].cla()
            output_data[ro_element] = np.array([fetch_data[0], fetch_data[1]])
            plot_crosstalk_3Dscalar( flux_crosstalk, flux_target, output_data[ro_element][0], z_line, ax[0])
            plot_crosstalk_3Dscalar( flux_crosstalk, flux_target, output_data[ro_element][1], z_line, ax[1])
            iteration = fetch_data[-1]
            # Progress bar
            progress_counter(iteration, n_avg, start_time=results.get_start_time())      

            plt.tight_layout()
            plt.pause(1) 

        qm.close()
        return output_data, flux_target, flux_crosstalk

def pi_z_offset( flux_modify_range, prob_q_name:str, ro_element:str, z_line:list, config, qmm:QuantumMachinesManager, evo_time=1, expect_crosstalk:float=1.0, n_avg:int=100, amp_ratio=0.5, initializer:tuple=None, simulate=True):
    """
    Mapping z offset crosstalk by qubit frequency 
    """
    a_min = -flux_modify_range
    a_max = flux_modify_range
    da = flux_modify_range/25

    flux_crosstalk = np.arange(a_min, a_max + da / 2, da)  # + da/2 to add a_max to amplitudes
    flux_target = np.arange(a_min, a_max - da / 2, da)*expect_crosstalk 
    evo_cc = (evo_time/4)*u.us
    # flux_target = np.arange(a_min*expect_crosstalk , (a_max + da / 2)*expect_crosstalk , da*expect_crosstalk/2 )#flux_crosstalk*expect_crosstalk 
    flux_target_len = len(flux_target) 
    flux_crosstalk_len = len(flux_crosstalk) 

    with program() as zc:
        iqdata_stream = multiRO_declare( ro_element )
        n = declare(int) 
        n_st = declare_stream()
        dc_1 = declare(fixed) 
        dc_2 = declare(fixed) 

        with for_(n, 0, n < n_avg, n + 1):
            
            with for_(*from_array(dc_1, flux_target)):
                
                with for_(*from_array(dc_2, flux_crosstalk)):

                    
                    # Init
                    if initializer is None:
                        wait(100*u.us)
                        #wait(thermalization_time * u.ns)
                    else:
                        try:
                            initializer[0](*initializer[1])
                        except:
                            print("Initializer didn't work!")
                            wait(100*u.us)

                    # Opration
                    # play("saturation"*amp(0.01), prob_q_name, duration=evo_cc)

                    play( "x180"*amp(amp_ratio), prob_q_name, duration=evo_cc )
                    set_dc_offset( z_line[0], "single", get_offset(z_line[0],config)+dc_1 )
                    set_dc_offset( z_line[1], "single", get_offset(z_line[1],config)+dc_2 )
                    align()
                    # wait(evo_cc) 
                    wait(25) 
                    set_dc_offset( z_line[0], "single", get_offset(z_line[0],config) )
                    set_dc_offset( z_line[1], "single", get_offset(z_line[1],config) )
                    align()
                    wait(25) 

                    # Readout
                    align()
                    multiRO_measurement(iqdata_stream, ro_element, weights="rotated_")
            save(n, n_st)
        with stream_processing():
            n_st.save("iteration")
            multiRO_pre_save( iqdata_stream, ro_element, (flux_target_len,flux_crosstalk_len) )
    
    if simulate:
        simulation_config = SimulationConfig(duration=10_000)  # In clock cycles = 4ns
        job = qmm.simulate(config, zc, simulation_config)
        job.get_simulated_samples().con1.plot()
        plt.show()
    else:
        qm = qmm.open_qm(config)
        job = qm.execute(zc)

        ro_ch_name = []
        ro_ch_name.append(f"{ro_element}_I")
        ro_ch_name.append(f"{ro_element}_Q")
        data_list = ro_ch_name + ["iteration"]   
        results = fetching_tool(job, data_list=data_list, mode="live")

        fig, ax = plt.subplots(2)
        interrupt_on_close(fig, job)
        # fig.colorbar( p_i, ax=ax[0] )
        # fig.colorbar( p_q, ax=ax[1] )


        output_data = {}
        while results.is_processing():
            fetch_data = results.fetch_all()
            plt.cla()
            ax[0].cla()
            ax[1].cla()
            output_data[ro_element] = np.array([fetch_data[0], fetch_data[1]])
            plot_crosstalk_3Dscalar( flux_crosstalk, flux_target, output_data[ro_element][0], z_line, ax[0])
            plot_crosstalk_3Dscalar( flux_crosstalk, flux_target, output_data[ro_element][1], z_line, ax[1])
            iteration = fetch_data[-1]
            # Progress bar
            progress_counter(iteration, n_avg, start_time=results.get_start_time())      

            plt.tight_layout()
            plt.pause(1) 

        qm.close()
        return output_data, flux_target, flux_crosstalk

def pi_z_pulse( flux_modify_range, prob_q_name:str, ro_element:str, z_line:list, config, qmm:QuantumMachinesManager, evo_time=1, expect_crosstalk:float=1.0, n_avg:int=100, amp_ratio=0.5, initializer:tuple=None, simulate=True):
    """
    Mapping z offset crosstalk by qubit frequency 
    """
    a_min = -flux_modify_range
    a_max = flux_modify_range
    da = flux_modify_range/100

    flux_crosstalk = np.arange(a_min, a_max + da / 2, da)  # + da/2 to add a_max to amplitudes
    flux_target = np.arange(a_min, a_max - da / 2, da)*expect_crosstalk 
    evo_cc = (evo_time/4)*u.us
    # flux_target = np.arange(a_min*expect_crosstalk , (a_max + da / 2)*expect_crosstalk , da*expect_crosstalk/2 )#flux_crosstalk*expect_crosstalk 
    flux_target_len = len(flux_target) 
    flux_crosstalk_len = len(flux_crosstalk) 

    with program() as zc:
        iqdata_stream = multiRO_declare( ro_element )
        n = declare(int) 
        n_st = declare_stream()
        dc_1 = declare(fixed) 
        dc_2 = declare(fixed) 

        with for_(n, 0, n < n_avg, n + 1):
            
            with for_(*from_array(dc_1, flux_target)):
                
                with for_(*from_array(dc_2, flux_crosstalk)):

                    
                    # Init
                    if initializer is None:
                        wait(100*u.us)
                        #wait(thermalization_time * u.ns)
                    else:
                        try:
                            initializer[0](*initializer[1])
                        except:
                            print("Initializer didn't work!")
                            wait(100*u.us)

                    # Opration
                    # play("saturation"*amp(0.01), prob_q_name, duration=evo_cc)
                    play( "x180"*amp(amp_ratio), prob_q_name, duration=evo_cc )
                    align()
                    wait(25)
                    play("const"*amp(dc_1*2.), z_line[0], evo_cc)         #const 預設0.5
                    play("const"*amp(dc_2*2.), z_line[1], evo_cc)
                    align()
                    wait(25)
                    # set_dc_offset( z_line[0], "single", get_offset(z_line[0],config) )
                    # set_dc_offset( z_line[1], "single", get_offset(z_line[1],config) )
                    # align()
                    # wait(25) 

                    # Readout
                    # align()
                    multiRO_measurement(iqdata_stream, ro_element, weights="rotated_")
            save(n, n_st)
        with stream_processing():
            n_st.save("iteration")
            multiRO_pre_save( iqdata_stream, ro_element, (flux_target_len,flux_crosstalk_len) )
    
    if simulate:
        simulation_config = SimulationConfig(duration=10_000)  # In clock cycles = 4ns
        job = qmm.simulate(config, zc, simulation_config)
        job.get_simulated_samples().con2.plot()
        plt.show()
    else:
        qm = qmm.open_qm(config)
        job = qm.execute(zc)

        ro_ch_name = []
        ro_ch_name.append(f"{ro_element}_I")
        ro_ch_name.append(f"{ro_element}_Q")
        data_list = ro_ch_name + ["iteration"]   
        results = fetching_tool(job, data_list=data_list, mode="live")

        fig, ax = plt.subplots(2)
        interrupt_on_close(fig, job)
        # fig.colorbar( p_i, ax=ax[0] )
        # fig.colorbar( p_q, ax=ax[1] )


        output_data = {}
        while results.is_processing():
            fetch_data = results.fetch_all()
            plt.cla()
            ax[0].cla()
            ax[1].cla()
            output_data[ro_element] = np.array([fetch_data[0], fetch_data[1]])
            plot_crosstalk_3Dscalar( flux_crosstalk, flux_target, output_data[ro_element][0], z_line, ax[0])
            plot_crosstalk_3Dscalar( flux_crosstalk, flux_target, output_data[ro_element][1], z_line, ax[1])
            iteration = fetch_data[-1]
            # Progress bar
            progress_counter(iteration, n_avg, start_time=results.get_start_time())      

            plt.tight_layout()
            plt.pause(1) 

        qm.close()
        return output_data, flux_target, flux_crosstalk

def plot_crosstalk_3Dscalar( x, y, z, z_line_name, ax=None ):
        if ax == None:
            fig, ax = plt.subplots(2)
        p_i = ax.pcolormesh( x, y, z, cmap='RdBu')

        # plt.colorbar( p_q, ax=ax[1] )
        ax.set_xlabel(f"{z_line_name[1]} Delta Voltage (V)")
        ax.set_ylabel(f"{z_line_name[0]} Delta Voltage (V)")

